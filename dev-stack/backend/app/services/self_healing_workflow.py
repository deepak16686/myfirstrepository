"""
Self-Healing Workflow Service

Orchestrates the complete self-healing pipeline flow:
1. Check ChromaDB for existing template
2. If not found, generate new template via LLM
3. Validate with dry-run
4. Fix validation errors if any (via LLM)
5. Commit to GitLab
6. Monitor pipeline execution
7. If failed, analyze and fix via LLM (max 10 retries)
8. If successful, store in ChromaDB for future use
"""
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

import httpx

from app.config import settings, tools_manager
from app.services.pipeline import pipeline_generator
from app.services.dry_run_validator import dry_run_validator, ValidationResult
from app.services.llm_fixer import llm_fixer, FixResult
from app.services.pipeline_progress import progress_store
from app.integrations.chromadb import ChromaDBIntegration
from app.integrations.llm_provider import get_active_provider_name


class WorkflowStatus(Enum):
    """Status of the self-healing workflow"""
    PENDING = "pending"
    CHECKING_TEMPLATE = "checking_template"
    GENERATING = "generating"
    VALIDATING = "validating"
    FIXING_VALIDATION = "fixing_validation"
    COMMITTING = "committing"
    RUNNING_PIPELINE = "running_pipeline"
    FIXING_PIPELINE = "fixing_pipeline"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class WorkflowState:
    """Current state of the workflow"""
    status: WorkflowStatus = WorkflowStatus.PENDING
    repo_url: str = ""
    language: str = ""
    framework: str = ""
    branch: str = ""
    project_id: int = 0
    pipeline_id: int = 0
    attempt: int = 0
    max_attempts: int = 10
    dockerfile: str = ""
    gitlab_ci: str = ""
    template_source: str = ""  # "chromadb", "llm_generated", "llm_fixed"
    errors: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        print(f"[SelfHealing] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "repo_url": self.repo_url,
            "language": self.language,
            "framework": self.framework,
            "branch": self.branch,
            "project_id": self.project_id,
            "pipeline_id": self.pipeline_id,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "template_source": self.template_source,
            "errors": self.errors,
            "logs": self.logs
        }


class SelfHealingWorkflow:
    """
    Orchestrates the complete self-healing pipeline workflow.

    Flow:
    1. Analyze repo → Get language/framework
    2. Check ChromaDB → Template exists?
       - YES → Use template directly
       - NO → Generate via LLM
    3. Dry-run validation
       - FAIL → LLM fixes validation errors
    4. Commit to GitLab
    5. Monitor pipeline
       - FAIL → LLM analyzes error and fixes (max 10 retries)
       - SUCCESS → Store in ChromaDB
    """

    PIPELINE_CHECK_INTERVAL = 30  # seconds
    PIPELINE_MAX_WAIT = 15 * 60   # 15 minutes

    def __init__(self):
        self.gitlab_url = settings.gitlab_url
        self.chromadb_config = tools_manager.get_tool("chromadb")

    def _get_chromadb(self) -> ChromaDBIntegration:
        return ChromaDBIntegration(self.chromadb_config)

    async def run(
        self,
        repo_url: str,
        gitlab_token: str,
        additional_context: str = "",
        auto_commit: bool = True,
        max_attempts: int = 10
    ) -> WorkflowState:
        """
        Run the complete self-healing workflow.

        Args:
            repo_url: GitLab repository URL
            gitlab_token: GitLab access token
            additional_context: Additional context for LLM
            auto_commit: Whether to automatically commit (default True)
            max_attempts: Maximum fix attempts (default 10)

        Returns:
            WorkflowState with final status and results
        """
        state = WorkflowState(
            repo_url=repo_url,
            max_attempts=max_attempts
        )

        try:
            # ═══════════════════════════════════════════════════════════════
            # STEP 1: Analyze Repository
            # ═══════════════════════════════════════════════════════════════
            state.status = WorkflowStatus.CHECKING_TEMPLATE
            state.log(f"Analyzing repository: {repo_url}")

            analysis = await pipeline_generator.analyze_repository(repo_url, gitlab_token)
            state.language = analysis.get('language', 'unknown')
            state.framework = analysis.get('framework', 'generic')
            state.log(f"Detected: {state.language}/{state.framework}")

            # ═══════════════════════════════════════════════════════════════
            # STEP 2: Check ChromaDB for Existing Template
            # ═══════════════════════════════════════════════════════════════
            state.log("Checking ChromaDB for existing template...")
            template_files = await pipeline_generator.get_best_template_files(
                state.language,
                state.framework
            )

            if template_files and template_files.get('gitlab_ci'):
                state.log("✓ Found existing template in ChromaDB!")
                state.dockerfile = template_files.get('dockerfile', '')
                state.gitlab_ci = template_files['gitlab_ci']
                state.template_source = "chromadb"

                # If no dockerfile in template, generate default
                if not state.dockerfile:
                    state.dockerfile = pipeline_generator._get_default_dockerfile(analysis)
            else:
                # ═══════════════════════════════════════════════════════════
                # STEP 3: Generate New Template via LLM
                # ═══════════════════════════════════════════════════════════
                state.status = WorkflowStatus.GENERATING
                state.log("No template found. Generating via LLM...")

                result = await pipeline_generator.generate_pipeline_files(
                    repo_url=repo_url,
                    gitlab_token=gitlab_token,
                    additional_context=additional_context,
                    use_template_only=False
                )

                state.dockerfile = result['dockerfile']
                state.gitlab_ci = result['gitlab_ci']
                state.template_source = "llm_generated"
                state.log(f"✓ Generated new template (model: {result.get('model_used', 'unknown')})")

            # ═══════════════════════════════════════════════════════════════
            # STEP 4: Dry-Run Validation
            # ═══════════════════════════════════════════════════════════════
            state.status = WorkflowStatus.VALIDATING
            state.log("Running dry-run validation...")

            validation_results = await dry_run_validator.validate_all(
                gitlab_ci=state.gitlab_ci,
                dockerfile=state.dockerfile,
                gitlab_token=gitlab_token
            )

            all_valid, validation_summary = dry_run_validator.get_validation_summary(validation_results)

            if not all_valid:
                state.log(f"Validation failed:\n{validation_summary}")

                # Collect all errors
                all_errors = []
                for check_name, result in validation_results.items():
                    all_errors.extend(result.errors)

                # ═══════════════════════════════════════════════════════════
                # STEP 4b: Fix Validation Errors via LLM
                # ═══════════════════════════════════════════════════════════
                state.status = WorkflowStatus.FIXING_VALIDATION
                state.log("Fixing validation errors via LLM...")

                fix_result = await llm_fixer.fix_validation_errors(
                    dockerfile=state.dockerfile,
                    gitlab_ci=state.gitlab_ci,
                    validation_errors=all_errors,
                    language=state.language,
                    framework=state.framework
                )

                if fix_result.success:
                    state.dockerfile = fix_result.dockerfile
                    state.gitlab_ci = fix_result.gitlab_ci
                    state.template_source = "llm_fixed"
                    state.log(f"✓ Fixed validation errors: {fix_result.explanation[:100]}")

                    # Re-validate
                    validation_results = await dry_run_validator.validate_all(
                        gitlab_ci=state.gitlab_ci,
                        dockerfile=state.dockerfile,
                        gitlab_token=gitlab_token
                    )
                    all_valid, _ = dry_run_validator.get_validation_summary(validation_results)

                    if not all_valid:
                        state.errors.append("Validation still failing after LLM fix")
                        state.log("⚠ Validation still failing, proceeding anyway...")
                else:
                    state.log(f"⚠ Could not fix validation errors: {fix_result.explanation}")
            else:
                state.log("✓ Validation passed!")

            # ═══════════════════════════════════════════════════════════════
            # STEP 5: Commit to GitLab
            # ═══════════════════════════════════════════════════════════════
            if not auto_commit:
                state.log("Auto-commit disabled. Returning generated files.")
                state.status = WorkflowStatus.SUCCESS
                return state

            state.status = WorkflowStatus.COMMITTING
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            state.branch = f"feature/ai-pipeline-{timestamp}"
            state.log(f"Committing to branch: {state.branch}")

            commit_result = await pipeline_generator.commit_to_gitlab(
                repo_url=repo_url,
                gitlab_token=gitlab_token,
                files={
                    ".gitlab-ci.yml": state.gitlab_ci,
                    "Dockerfile": state.dockerfile
                },
                branch_name=state.branch,
                commit_message="Add CI/CD pipeline configuration [AI Self-Healing]"
            )

            state.project_id = commit_result['project_id']
            state.log(f"✓ Committed (commit: {commit_result['commit_id'][:8]})")

            # ═══════════════════════════════════════════════════════════════
            # STEP 6: Monitor Pipeline Execution
            # ═══════════════════════════════════════════════════════════════
            state.status = WorkflowStatus.RUNNING_PIPELINE
            state.log("Monitoring pipeline execution...")

            pipeline_result = await self._monitor_pipeline(
                state=state,
                gitlab_token=gitlab_token
            )

            if pipeline_result['success']:
                # ═══════════════════════════════════════════════════════════
                # STEP 7: SUCCESS - Store in ChromaDB
                # ═══════════════════════════════════════════════════════════
                state.status = WorkflowStatus.SUCCESS
                state.log("✓ Pipeline succeeded!")

                # Store in ChromaDB for future use (only if all stages passed)
                stored = await self._store_successful_template(state, gitlab_token)
                if stored:
                    state.log("✓ Template stored in ChromaDB for future use")

            else:
                # ═══════════════════════════════════════════════════════════
                # STEP 8: Pipeline Failed - Auto-Fix Loop
                # ═══════════════════════════════════════════════════════════
                ps = pipeline_result.get('status', 'failed')
                if ps == 'partial_success':
                    state.log(f"Pipeline succeeded but some jobs failed. Starting auto-fix loop (max {max_attempts} attempts)...")
                else:
                    state.log(f"Pipeline failed. Starting auto-fix loop (max {max_attempts} attempts)...")

                while state.attempt < max_attempts:
                    state.attempt += 1
                    state.status = WorkflowStatus.FIXING_PIPELINE
                    state.log(f"Fix attempt {state.attempt}/{max_attempts}")

                    # Get failed job info
                    failed_job = pipeline_result.get('failed_job', {})
                    job_id = failed_job.get('id')
                    job_name = failed_job.get('name', 'unknown')

                    if job_id:
                        # Generate fix via LLM
                        fix_result = await llm_fixer.fix_from_job_log(
                            dockerfile=state.dockerfile,
                            gitlab_ci=state.gitlab_ci,
                            job_id=job_id,
                            project_id=state.project_id,
                            gitlab_token=gitlab_token,
                            language=state.language,
                            framework=state.framework
                        )

                        if fix_result.success:
                            state.dockerfile = fix_result.dockerfile
                            state.gitlab_ci = fix_result.gitlab_ci
                            state.template_source = "llm_fixed"
                            state.log(f"Fix applied: {fix_result.explanation[:100]}")

                            # Commit fix
                            await pipeline_generator.commit_to_gitlab(
                                repo_url=repo_url,
                                gitlab_token=gitlab_token,
                                files={
                                    ".gitlab-ci.yml": state.gitlab_ci,
                                    "Dockerfile": state.dockerfile
                                },
                                branch_name=state.branch,
                                commit_message=f"AI Fix attempt {state.attempt}: {fix_result.error_identified}"
                            )

                            # Monitor new pipeline
                            state.status = WorkflowStatus.RUNNING_PIPELINE
                            pipeline_result = await self._monitor_pipeline(
                                state=state,
                                gitlab_token=gitlab_token
                            )

                            if pipeline_result['success']:
                                state.status = WorkflowStatus.SUCCESS
                                state.log(f"✓ Pipeline succeeded after {state.attempt} fix(es)!")
                                stored = await self._store_successful_template(state, gitlab_token)
                                if stored:
                                    state.log("✓ Fixed template stored in ChromaDB")
                                break
                        else:
                            state.log(f"Fix generation failed: {fix_result.explanation}")
                    else:
                        state.log("Could not identify failed job")
                        break

                if state.status != WorkflowStatus.SUCCESS:
                    state.status = WorkflowStatus.FAILED
                    state.errors.append(f"Failed after {state.attempt} fix attempts")
                    state.log(f"✗ Pipeline still failing after {state.attempt} attempts")

                    # Create GitLab issue for manual review
                    await self._create_failure_issue(state, gitlab_token)

        except Exception as e:
            state.status = WorkflowStatus.FAILED
            state.errors.append(str(e))
            state.log(f"✗ Workflow error: {str(e)}")

        return state

    async def _monitor_pipeline(
        self,
        state: WorkflowState,
        gitlab_token: str
    ) -> Dict[str, Any]:
        """
        Monitor pipeline execution until completion.
        Returns dict with success status and failed job info if applicable.
        """
        start_time = datetime.now()
        pipeline_id = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"PRIVATE-TOKEN": gitlab_token}

            while (datetime.now() - start_time).total_seconds() < self.PIPELINE_MAX_WAIT:
                try:
                    # Get latest pipeline for branch
                    resp = await client.get(
                        f"{self.gitlab_url}/api/v4/projects/{state.project_id}/pipelines",
                        headers=headers,
                        params={"ref": state.branch, "per_page": 1}
                    )

                    if resp.status_code == 200:
                        pipelines = resp.json()
                        if pipelines:
                            pipeline = pipelines[0]
                            pipeline_id = pipeline['id']
                            status = pipeline['status']
                            state.pipeline_id = pipeline_id

                            if status == 'success':
                                # Check if ALL jobs truly passed (allow_failure jobs may have failed)
                                all_passed = await self._all_stages_passed(
                                    state.project_id, pipeline_id, gitlab_token)
                                if all_passed:
                                    return {"success": True, "pipeline_id": pipeline_id}
                                else:
                                    # Pipeline "succeeded" but some allow_failure jobs failed
                                    # Find the failed job so self-healing can fix it
                                    jobs_resp = await client.get(
                                        f"{self.gitlab_url}/api/v4/projects/{state.project_id}/pipelines/{pipeline_id}/jobs",
                                        headers=headers
                                    )
                                    failed_job = None
                                    if jobs_resp.status_code == 200:
                                        jobs = jobs_resp.json()
                                        # Find failed jobs, skip notify_failure (expected)
                                        for j in jobs:
                                            if j['status'] == 'failed' and j.get('name') != 'notify_failure':
                                                failed_job = j
                                                break
                                    state.log(f"Pipeline {pipeline_id} succeeded but job '{failed_job.get('name', '?') if failed_job else '?'}' failed — continuing self-heal")
                                    return {
                                        "success": False,
                                        "pipeline_id": pipeline_id,
                                        "status": "partial_success",
                                        "failed_job": failed_job
                                    }

                            elif status in ['failed', 'canceled']:
                                # Get failed job
                                jobs_resp = await client.get(
                                    f"{self.gitlab_url}/api/v4/projects/{state.project_id}/pipelines/{pipeline_id}/jobs",
                                    headers=headers
                                )
                                if jobs_resp.status_code == 200:
                                    jobs = jobs_resp.json()
                                    failed_job = next(
                                        (j for j in jobs if j['status'] == 'failed'),
                                        None
                                    )
                                    return {
                                        "success": False,
                                        "pipeline_id": pipeline_id,
                                        "status": status,
                                        "failed_job": failed_job
                                    }
                                return {"success": False, "pipeline_id": pipeline_id, "status": status}

                            elif status in ['pending', 'running', 'created']:
                                state.log(f"Pipeline {pipeline_id}: {status}...")

                except Exception as e:
                    state.log(f"Error checking pipeline: {e}")

                await asyncio.sleep(self.PIPELINE_CHECK_INTERVAL)

        return {"success": False, "pipeline_id": pipeline_id, "status": "timeout"}

    async def _store_successful_template(self, state: WorkflowState, gitlab_token: str = "") -> bool:
        """Store successful template in ChromaDB — only if ALL stages passed.

        Returns True if template was stored, False otherwise.
        """
        try:
            # QUALITY GATE: Check all jobs passed before saving
            if state.pipeline_id and state.project_id and gitlab_token:
                all_passed = await self._all_stages_passed(
                    state.project_id, state.pipeline_id, gitlab_token)
                if not all_passed:
                    state.log("Template NOT saved to RAG — not all stages passed (some failed/skipped)")
                    return False

            await pipeline_generator.store_manual_template(
                language=state.language,
                framework=state.framework,
                gitlab_ci=state.gitlab_ci,
                dockerfile=state.dockerfile,
                description=f"Auto-generated and tested (source: {state.template_source})"
            )
            return True
        except Exception as e:
            state.log(f"Warning: Could not store template in ChromaDB: {e}")
            return False

    async def _all_stages_passed(self, project_id: int, pipeline_id: int, gitlab_token: str) -> bool:
        """Check if ALL pipeline jobs passed (no failures/skips except notify_failure)."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.gitlab_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs",
                    headers={"PRIVATE-TOKEN": gitlab_token}
                )
                if resp.status_code != 200:
                    return False
                jobs = resp.json()
                for job in jobs:
                    name = job.get('name', '')
                    status = job.get('status', '')
                    # notify_failure is expected to be skipped (when: on_failure)
                    if name == 'notify_failure' and status == 'skipped':
                        continue
                    # learn_record may still be running (it's the caller)
                    if name == 'learn_record' and status in ('running', 'success'):
                        continue
                    if status not in ('success',):
                        print(f"[RL] Quality gate: job '{name}' has status '{status}' — NOT saving to RAG")
                        return False
                return True
        except Exception as e:
            print(f"[RL] Quality gate check failed: {e}")
            return False

    async def _get_failed_job(
        self,
        project_id: int,
        pipeline_id: int,
        gitlab_token: str
    ) -> Optional[Dict[str, Any]]:
        """Find the root-cause failed job in a pipeline (earliest stage)."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.gitlab_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs",
                    headers={"PRIVATE-TOKEN": gitlab_token}
                )
                if resp.status_code == 200:
                    jobs = resp.json()
                    failed_jobs = [j for j in jobs if j['status'] == 'failed']
                    if not failed_jobs:
                        return None
                    # GitLab returns jobs with latest stages first.
                    # Reverse to get earliest-stage jobs first (root cause).
                    # Also skip notify jobs (when: on_failure) since they're
                    # symptoms, not root causes.
                    failed_jobs.reverse()
                    for job in failed_jobs:
                        if job.get('name', '').startswith('notify_'):
                            continue
                        return job
                    # If only notify jobs failed, return the first one
                    return failed_jobs[0]
        except Exception as e:
            print(f"[SelfHealing] Error fetching failed job: {e}")
        return None

    async def _get_yaml_error(
        self,
        project_id: int,
        branch: str,
        gitlab_token: str
    ) -> Optional[str]:
        """
        Check if pipeline failed due to YAML syntax errors (no jobs created).
        Lints the .gitlab-ci.yml via GitLab CI Lint API and returns the error.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {"PRIVATE-TOKEN": gitlab_token}
                # Fetch .gitlab-ci.yml content
                file_resp = await client.get(
                    f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/files/.gitlab-ci.yml/raw",
                    headers=headers,
                    params={"ref": branch}
                )
                if file_resp.status_code != 200:
                    return None

                # Lint it
                lint_resp = await client.post(
                    f"{self.gitlab_url}/api/v4/projects/{project_id}/ci/lint",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"content": file_resp.text}
                )
                if lint_resp.status_code == 200:
                    lint = lint_resp.json()
                    if not lint.get("valid") and lint.get("errors"):
                        return "YAML syntax error in .gitlab-ci.yml:\n" + "\n".join(lint["errors"])
        except Exception as e:
            print(f"[SelfHealing] Error checking YAML lint: {e}")
        return None

    async def fix_existing_pipeline(
        self,
        repo_url: str,
        gitlab_token: str,
        project_id: int,
        pipeline_id: int,
        branch: str,
        language: str = "unknown",
        framework: str = "generic",
        dockerfile: str = "",
        gitlab_ci: str = "",
        max_attempts: int = 10
    ) -> WorkflowState:
        """
        Lighter self-healing workflow for already-committed pipelines.

        Skips analyze/generate/validate steps and goes straight to the
        fix loop. Used when monitor_pipeline_for_learning() detects a failure.

        Args:
            repo_url: GitLab repository URL
            gitlab_token: GitLab access token
            project_id: GitLab project ID
            pipeline_id: Failed pipeline ID
            branch: Branch where pipeline is running
            language: Detected language
            framework: Detected framework
            dockerfile: Current Dockerfile content
            gitlab_ci: Current .gitlab-ci.yml content
            max_attempts: Maximum fix attempts (default 10)

        Returns:
            WorkflowState with final status and results
        """
        state = WorkflowState(
            repo_url=repo_url,
            project_id=project_id,
            pipeline_id=pipeline_id,
            branch=branch,
            language=language,
            framework=framework,
            dockerfile=dockerfile,
            gitlab_ci=gitlab_ci,
            max_attempts=max_attempts
        )

        state.log(f"Starting auto-fix for failed pipeline {pipeline_id} on {branch}")
        progress_store.update(project_id, branch, "fixing",
            f"Starting auto-fix for failed pipeline #{pipeline_id}...")

        try:
            # ═══════════════════════════════════════════════════════════
            # Auto-Fix Loop (reuses pattern from run() lines 298-363)
            # ═══════════════════════════════════════════════════════════
            while state.attempt < max_attempts:
                state.attempt += 1
                state.status = WorkflowStatus.FIXING_PIPELINE
                state.log(f"Fix attempt {state.attempt}/{max_attempts}")
                progress_store.update(project_id, branch, "fixing",
                    f"Fix attempt {state.attempt}/{max_attempts}: Analyzing failed job...",
                    attempt=state.attempt)

                # Get failed job from the current pipeline
                failed_job = await self._get_failed_job(
                    project_id=project_id,
                    pipeline_id=state.pipeline_id,
                    gitlab_token=gitlab_token
                )

                fix_result = None

                if failed_job:
                    # Case 1: Normal job failure — get fix from job log
                    job_id = failed_job['id']
                    job_name = failed_job.get('name', 'unknown')
                    state.log(f"Failed job: {job_name} (ID: {job_id})")
                    progress_store.update(project_id, branch, "fixing",
                        f"Fix attempt {state.attempt}/{max_attempts}: Failed job '{job_name}' — LLM generating fix...",
                        attempt=state.attempt)

                    fix_result = await llm_fixer.fix_from_job_log(
                        dockerfile=state.dockerfile,
                        gitlab_ci=state.gitlab_ci,
                        job_id=job_id,
                        project_id=project_id,
                        gitlab_token=gitlab_token,
                        language=state.language,
                        framework=state.framework
                    )
                else:
                    # Case 2: No jobs at all — likely YAML syntax error
                    yaml_error = await self._get_yaml_error(
                        project_id=project_id,
                        branch=branch,
                        gitlab_token=gitlab_token
                    )
                    if yaml_error:
                        state.log(f"YAML error detected: {yaml_error[:100]}")
                        fix_result = await llm_fixer.generate_fix(
                            dockerfile=state.dockerfile,
                            gitlab_ci=state.gitlab_ci,
                            error_log=yaml_error,
                            job_name="yaml_validation",
                            language=state.language,
                            framework=state.framework
                        )
                    else:
                        state.log("Could not identify failed job or YAML error")
                        break

                if not fix_result.success:
                    state.log(f"Fix generation failed: {fix_result.explanation}")
                    continue

                state.dockerfile = fix_result.dockerfile
                state.gitlab_ci = fix_result.gitlab_ci
                state.template_source = "llm_fixed"
                state.log(f"Fix applied: {fix_result.explanation[:100]}")

                # Track fixer model on progress
                progress = progress_store.get(project_id, branch)
                if progress:
                    progress.fixer_model_used = get_active_provider_name()

                # Validate and auto-correct images for the detected language
                state.gitlab_ci, state.dockerfile, img_fixes = pipeline_generator.validate_and_fix_pipeline_images(
                    state.gitlab_ci, state.dockerfile, state.language
                )
                if img_fixes:
                    state.log(f"Image validator corrected {len(img_fixes)} issues: {', '.join(img_fixes[:3])}")

                # Commit fix directly (not via HTTP endpoint to avoid re-triggering monitor)
                try:
                    commit_result = await pipeline_generator.commit_to_gitlab(
                        repo_url=repo_url,
                        gitlab_token=gitlab_token,
                        files={
                            ".gitlab-ci.yml": state.gitlab_ci,
                            "Dockerfile": state.dockerfile
                        },
                        branch_name=branch,
                        commit_message=f"AI Fix attempt {state.attempt}: {fix_result.error_identified}"
                    )
                    state.log(f"Fix committed (commit: {commit_result['commit_id'][:8]})")
                    progress_store.update(project_id, branch, "fix_committed",
                        f"Fix attempt {state.attempt}/{max_attempts}: Fix committed, monitoring new pipeline...",
                        attempt=state.attempt)
                except Exception as commit_err:
                    state.log(f"Commit failed (attempt {state.attempt}): {str(commit_err)[:120]}")
                    state.errors.append(f"Commit error attempt {state.attempt}: {str(commit_err)[:200]}")
                    continue  # Try next fix attempt

                # Monitor new pipeline using internal method (no recursion)
                try:
                    state.status = WorkflowStatus.RUNNING_PIPELINE
                    pipeline_result = await self._monitor_pipeline(
                        state=state,
                        gitlab_token=gitlab_token
                    )

                    if pipeline_result['success']:
                        state.status = WorkflowStatus.SUCCESS
                        state.log(f"Pipeline succeeded after {state.attempt} fix(es)!")
                        progress_store.complete(project_id, branch, "success",
                            f"Pipeline fixed successfully after {state.attempt} attempt(s)!")

                        # Store in ChromaDB for future use (only if all stages passed)
                        stored = await self._store_successful_template(state, gitlab_token)
                        if stored:
                            state.log("Fixed template stored in ChromaDB")
                        return state
                    else:
                        # Update pipeline_id for next iteration
                        state.pipeline_id = pipeline_result.get('pipeline_id', state.pipeline_id)
                        state.log(f"Pipeline still failing after fix attempt {state.attempt}")
                except Exception as monitor_err:
                    state.log(f"Monitor failed (attempt {state.attempt}): {str(monitor_err)[:120]}")
                    state.errors.append(f"Monitor error attempt {state.attempt}: {str(monitor_err)[:200]}")
                    continue  # Try next fix attempt

            # All attempts exhausted
            state.status = WorkflowStatus.FAILED
            state.errors.append(f"Failed after {state.attempt} fix attempts")
            state.log(f"Pipeline still failing after {state.attempt} attempts")
            progress_store.complete(project_id, branch, "failed",
                f"Self-healing failed after {state.attempt} attempts. GitLab issue created for manual review.")

            # Create GitLab issue for manual review
            await self._create_failure_issue(state, gitlab_token)

        except Exception as e:
            state.status = WorkflowStatus.FAILED
            state.errors.append(str(e))
            state.log(f"Auto-fix error: {str(e)}")
            progress_store.complete(project_id, branch, "failed",
                f"Auto-fix error: {str(e)[:100]}")

        return state

    async def _create_failure_issue(self, state: WorkflowState, gitlab_token: str):
        """Create a GitLab issue for failed pipelines that need manual review"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                issue_body = f"""
## AI Pipeline Generation Failed

The self-healing workflow was unable to fix this pipeline after {state.attempt} attempts.

### Repository
- URL: {state.repo_url}
- Language: {state.language}
- Framework: {state.framework}
- Branch: {state.branch}

### Errors
{chr(10).join(f'- {e}' for e in state.errors)}

### Workflow Logs
```
{chr(10).join(state.logs[-20:])}
```

### Generated Files

<details>
<summary>Dockerfile</summary>

```dockerfile
{state.dockerfile}
```
</details>

<details>
<summary>.gitlab-ci.yml</summary>

```yaml
{state.gitlab_ci}
```
</details>

---
*This issue was created automatically by the AI Self-Healing Pipeline system.*
"""
                await client.post(
                    f"{self.gitlab_url}/api/v4/projects/{state.project_id}/issues",
                    headers={"PRIVATE-TOKEN": gitlab_token},
                    json={
                        "title": f"[AI Pipeline] Auto-fix failed for {state.language}/{state.framework}",
                        "description": issue_body,
                        "labels": "ai-pipeline,needs-review"
                    }
                )
                state.log("Created GitLab issue for manual review")
        except Exception as e:
            state.log(f"Could not create failure issue: {e}")


# Singleton instance
self_healing_workflow = SelfHealingWorkflow()
