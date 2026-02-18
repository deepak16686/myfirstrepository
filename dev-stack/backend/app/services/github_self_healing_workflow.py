"""
File: github_self_healing_workflow.py
Purpose: Orchestrates the complete end-to-end self-healing pipeline for GitHub Actions: analyzes
    the repository, generates a workflow (from ChromaDB template or LLM), validates with the dry-run
    validator, iteratively fixes errors via the LLM fixer, commits to the repository, monitors
    workflow execution by polling Gitea Actions, records successful results for RL, and creates a
    GitHub/Gitea issue if all attempts fail.
When Used: Called by the /self-heal endpoint when a user requests fully automated pipeline
    generation with no manual approval steps. Runs the entire lifecycle autonomously, including
    re-attempting fixes from runtime logs if the committed workflow fails.
Why Created: Kept as a standalone orchestrator outside the github_pipeline package because it
    composes multiple independent services (generator, dry-run validator, LLM fixer, committer,
    status monitor) into a single automated workflow that would not fit cleanly inside any one
    of those modules.
"""
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.config import settings
from app.services.github_pipeline import github_pipeline_generator
from app.services.github_dry_run_validator import github_dry_run_validator
from app.services.github_llm_fixer import github_llm_fixer


@dataclass
class WorkflowState:
    """State of the self-healing workflow"""
    repo_url: str
    github_token: str
    branch: Optional[str] = None
    workflow: Optional[str] = None
    dockerfile: Optional[str] = None
    analysis: Dict[str, Any] = field(default_factory=dict)
    attempt: int = 0
    max_attempts: int = 3
    status: str = "pending"
    errors: list = field(default_factory=list)
    run_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "branch": self.branch,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "status": self.status,
            "errors": self.errors,
            "analysis": self.analysis,
            "run_id": self.run_id
        }


class GitHubSelfHealingWorkflow:
    """
    Orchestrates the complete self-healing workflow for GitHub Actions.
    """

    WORKFLOW_CHECK_INTERVAL = 30  # seconds
    WORKFLOW_MAX_WAIT = 15 * 60   # 15 minutes

    def __init__(self):
        self.chromadb_url = settings.chromadb_url

    async def run(
        self,
        repo_url: str,
        github_token: str,
        additional_context: str = "",
        auto_commit: bool = True,
        max_attempts: int = 3,
        runner_type: str = "self-hosted"
    ) -> Dict[str, Any]:
        """
        Run the complete self-healing workflow.

        Steps:
        1. Analyze repository
        2. Generate workflow (from template or LLM)
        3. Validate with dry-run
        4. Fix errors if validation fails (up to max_attempts)
        5. Commit to repository
        6. Monitor workflow execution
        7. Store successful template for RL
        """
        state = WorkflowState(
            repo_url=repo_url,
            github_token=github_token,
            max_attempts=max_attempts
        )

        try:
            # Step 1: Analyze repository
            print(f"[SelfHeal] Analyzing repository: {repo_url}")
            state.analysis = await github_pipeline_generator.analyze_repository(
                repo_url, github_token
            )
            state.status = "analyzed"

            # Step 2: Generate workflow
            print(f"[SelfHeal] Generating workflow for {state.analysis['language']}")
            generation_result = await github_pipeline_generator.generate_workflow_files(
                repo_url=repo_url,
                github_token=github_token,
                additional_context=additional_context,
                runner_type=runner_type
            )

            state.workflow = generation_result["workflow"]
            state.dockerfile = generation_result["dockerfile"]
            state.status = "generated"

            # Step 3-4: Validate and fix loop
            while state.attempt < state.max_attempts:
                state.attempt += 1
                print(f"[SelfHeal] Attempt {state.attempt}/{state.max_attempts}")

                # Validate
                validation_results = await github_dry_run_validator.validate_all(
                    workflow=state.workflow,
                    dockerfile=state.dockerfile,
                    github_token=github_token
                )

                all_valid, summary = github_dry_run_validator.get_validation_summary(
                    validation_results
                )

                if all_valid:
                    print(f"[SelfHeal] Validation passed")
                    state.status = "validated"
                    break

                print(f"[SelfHeal] Validation failed: {summary}")
                state.errors.append({
                    "attempt": state.attempt,
                    "validation_summary": summary
                })

                # Try to fix with LLM
                if state.attempt < state.max_attempts:
                    print(f"[SelfHeal] Attempting LLM fix")
                    fix_result = await github_llm_fixer.generate_fix(
                        dockerfile=state.dockerfile,
                        workflow=state.workflow,
                        error_log=summary,
                        job_name="validation",
                        language=state.analysis.get("language", "unknown"),
                        framework=state.analysis.get("framework", "generic")
                    )

                    if fix_result.success:
                        state.workflow = fix_result.workflow
                        state.dockerfile = fix_result.dockerfile
                        print(f"[SelfHeal] LLM fix applied: {fix_result.explanation}")
                    else:
                        print(f"[SelfHeal] LLM fix failed: {fix_result.explanation}")

            # Step 5: Commit if auto_commit enabled
            if auto_commit and state.status == "validated":
                print(f"[SelfHeal] Committing to repository")
                commit_result = await github_pipeline_generator.commit_to_github(
                    repo_url=repo_url,
                    github_token=github_token,
                    workflow=state.workflow,
                    dockerfile=state.dockerfile
                )

                if commit_result.get("success"):
                    state.branch = commit_result["branch"]
                    state.status = "committed"
                    print(f"[SelfHeal] Committed to branch: {state.branch}")

                    # Step 6: Monitor workflow execution
                    print(f"[SelfHeal] Monitoring workflow execution")
                    run_result = await self._monitor_workflow(state, github_token)

                    if run_result.get("success"):
                        state.status = "success"
                        state.run_id = run_result.get("run_id")

                        # Step 7: Store successful template (only if all jobs passed)
                        stored = await self._store_successful_template(state)
                        if stored:
                            print(f"[SelfHeal] Workflow completed successfully — template stored!")
                        else:
                            print(f"[SelfHeal] Workflow completed but template NOT stored (quality gate)")
                    else:
                        state.status = "workflow_failed"
                        state.errors.append({
                            "type": "workflow_execution",
                            "message": run_result.get("error", "Workflow execution failed")
                        })

                        # Try to fix from run logs
                        if run_result.get("run_id") and state.attempt < state.max_attempts:
                            await self._fix_from_run(state, github_token, runner_type)
                else:
                    state.status = "commit_failed"
                    state.errors.append({
                        "type": "commit",
                        "message": commit_result.get("error", "Commit failed")
                    })
            elif state.status != "validated":
                state.status = "validation_failed"

            # Create issue if failed
            if state.status in ["validation_failed", "workflow_failed", "commit_failed"]:
                await self._create_failure_issue(state, github_token)

        except Exception as e:
            state.status = "error"
            state.errors.append({
                "type": "exception",
                "message": str(e)
            })
            print(f"[SelfHeal] Error: {e}")

        return {
            "success": state.status == "success",
            "state": state.to_dict(),
            "workflow": state.workflow,
            "dockerfile": state.dockerfile
        }

    async def _monitor_workflow(
        self,
        state: WorkflowState,
        github_token: str
    ) -> Dict[str, Any]:
        """Monitor workflow execution until completion"""
        start_time = datetime.now()

        while True:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > self.WORKFLOW_MAX_WAIT:
                return {"success": False, "error": "Timeout waiting for workflow"}

            try:
                status = await github_pipeline_generator.get_workflow_status(
                    state.repo_url, github_token, state.branch
                )

                if status.get("status") == "completed":
                    conclusion = status.get("conclusion")
                    if conclusion == "success":
                        return {
                            "success": True,
                            "run_id": status.get("run_id")
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Workflow failed: {conclusion}",
                            "run_id": status.get("run_id")
                        }

                await asyncio.sleep(self.WORKFLOW_CHECK_INTERVAL)

            except Exception as e:
                print(f"[SelfHeal] Monitor error: {e}")
                await asyncio.sleep(self.WORKFLOW_CHECK_INTERVAL)

    async def _fix_from_run(
        self,
        state: WorkflowState,
        github_token: str,
        runner_type: str
    ):
        """Attempt to fix from workflow run logs"""
        print(f"[SelfHeal] Attempting fix from run logs")

        parsed = github_pipeline_generator.parse_github_url(state.repo_url)

        fix_result = await github_llm_fixer.fix_from_run_log(
            dockerfile=state.dockerfile,
            workflow=state.workflow,
            run_id=state.run_id,
            owner=parsed["owner"],
            repo=parsed["repo"],
            github_token=github_token,
            language=state.analysis.get("language", "unknown"),
            framework=state.analysis.get("framework", "generic")
        )

        if fix_result.success:
            state.workflow = fix_result.workflow
            state.dockerfile = fix_result.dockerfile
            state.attempt += 1

            # Re-commit and monitor
            commit_result = await github_pipeline_generator.commit_to_github(
                repo_url=state.repo_url,
                github_token=github_token,
                workflow=state.workflow,
                dockerfile=state.dockerfile,
                branch_name=state.branch
            )

            if commit_result.get("success"):
                run_result = await self._monitor_workflow(state, github_token)
                if run_result.get("success"):
                    state.status = "success"
                    state.run_id = run_result.get("run_id")
                    stored = await self._store_successful_template(state)
                    if stored:
                        print("[SelfHeal] Fixed template stored in ChromaDB")

    async def _store_successful_template(self, state: WorkflowState) -> bool:
        """Store successful template in ChromaDB for RL — only if ALL jobs passed.

        Returns True if template was stored, False otherwise.
        """
        try:
            # QUALITY GATE: Verify all workflow jobs passed before storing.
            if not state.run_id:
                print("[SelfHeal] Template NOT saved to RAG — no run_id to verify")
                return False

            all_passed = await self._all_jobs_passed(state)
            if not all_passed:
                print("[SelfHeal] Template NOT saved to RAG — not all jobs passed")
                return False

            # Use the learning module's proper storage function instead of raw ChromaDB API
            from app.services.github_pipeline.learning import store_successful_pipeline

            stored = await store_successful_pipeline(
                repo_url=state.repo_url,
                run_id=state.run_id,
                workflow_content=state.workflow or "",
                dockerfile_content=state.dockerfile or "",
                language=state.analysis.get("language", "unknown"),
                framework=state.analysis.get("framework", "generic"),
            )
            if stored:
                print(f"[SelfHeal] Stored successful template for {state.analysis.get('language')}/{state.analysis.get('framework')}")
            return stored

        except Exception as e:
            print(f"[SelfHeal] Failed to store template: {e}")
            return False

    async def _all_jobs_passed(self, state: WorkflowState) -> bool:
        """Check if ALL workflow jobs passed (no failures except learn-record/notify-failure)."""
        try:
            import httpx

            parsed = github_pipeline_generator.parse_github_url(state.repo_url)
            api_base = f"{parsed['host']}/api/v1/repos/{parsed['owner']}/{parsed['repo']}"
            headers = {"Authorization": f"token {state.github_token}"}

            async with httpx.AsyncClient(timeout=30.0) as client:
                jobs_resp = await client.get(
                    f"{api_base}/actions/runs/{state.run_id}/jobs",
                    headers=headers
                )
                if jobs_resp.status_code != 200:
                    print(f"[SelfHeal] Quality gate: could not fetch jobs (status {jobs_resp.status_code})")
                    return False

                jobs_data = jobs_resp.json()
                jobs_list = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else jobs_data

                # Exclude learn-record (still running) and notify-failure (skipped on success)
                skip_names = {"learn-record", "notify-failure"}
                non_learn_jobs = [j for j in jobs_list if j.get("name") not in skip_names]

                if not non_learn_jobs:
                    print("[SelfHeal] Quality gate: no jobs found to verify")
                    return False

                for job in non_learn_jobs:
                    conclusion = job.get("conclusion", "")
                    if conclusion != "success":
                        print(f"[SelfHeal] Quality gate: job '{job.get('name')}' has conclusion '{conclusion}' — NOT saving")
                        return False

                print(f"[SelfHeal] Quality gate: all {len(non_learn_jobs)} jobs passed")
                return True

        except Exception as e:
            print(f"[SelfHeal] Quality gate check failed: {e}")
            return False

    async def _create_failure_issue(
        self,
        state: WorkflowState,
        github_token: str
    ):
        """Create GitHub issue for failed workflow"""
        try:
            from app.integrations.github import GitHubIntegration
            from app.config import ToolConfig

            parsed = github_pipeline_generator.parse_github_url(state.repo_url)

            config = ToolConfig(
                base_url=parsed["host"],
                token=github_token
            )
            github = GitHubIntegration(config)

            error_summary = "\n".join([
                f"- Attempt {e.get('attempt', 'N/A')}: {e.get('validation_summary', e.get('message', 'Unknown error'))}"
                for e in state.errors
            ])

            body = f"""## Self-Healing Workflow Failed

The automated CI/CD pipeline generation failed after {state.attempt} attempts.

### Repository Analysis
- Language: {state.analysis.get('language', 'unknown')}
- Framework: {state.analysis.get('framework', 'generic')}

### Errors Encountered
{error_summary}

### Status
- Final Status: {state.status}
- Branch: {state.branch or 'Not created'}

### Next Steps
1. Review the errors above
2. Manually fix the workflow configuration
3. Commit to trigger a new pipeline run

---
*Generated by DevOps Tools Backend - Self-Healing Workflow*
"""

            await github.create_issue(
                owner=parsed["owner"],
                repo=parsed["repo"],
                title=f"[CI/CD] Self-healing workflow failed for {state.analysis.get('language', 'unknown')} project",
                body=body,
                labels=["ci-cd", "automated", "needs-attention"]
            )

            await github.close()
            print(f"[SelfHeal] Created failure issue")

        except Exception as e:
            print(f"[SelfHeal] Failed to create issue: {e}")


# Singleton instance
github_self_healing_workflow = GitHubSelfHealingWorkflow()
