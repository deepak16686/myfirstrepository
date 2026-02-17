"""
Pipeline Generator API Router

Provides endpoints for:
1. Generating GitLab CI/CD pipelines and Dockerfiles
2. Committing to GitLab repositories
3. Monitoring pipeline status
4. Storing and retrieving feedback for reinforcement learning
5. Automatic reinforcement learning from pipeline results
"""
import asyncio
import httpx
import traceback
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

from app.services.pipeline import pipeline_generator
from app.services.gitlab_dry_run_validator import gitlab_dry_run_validator
from app.services.self_healing_workflow import self_healing_workflow, WorkflowStatus
from app.services.pipeline_progress import progress_store
from app.services.dry_run_validator import dry_run_validator
from app.services.llm_fixer import llm_fixer
from app.integrations.llm_provider import get_active_provider_name

from app.models.pipeline_schemas import (
    GeneratePipelineRequest, GeneratePipelineResponse,
    GenerateWithValidationRequest, GenerateWithValidationResponse,
    CommitRequest, CommitResponse,
    PipelineStatusRequest, DryRunRequest, DryRunResponse,
    FeedbackRequest, FullWorkflowRequest,
    RecordPipelineResultRequest, StoreTemplateRequest,
    SelfHealRequest, FixRequest, FixFromJobRequest,
)

router = APIRouter(prefix="/pipeline", tags=["Pipeline Generator"])


# ============================================================================
# Background Tasks
# ============================================================================

async def _fetch_pipeline_files(
    project_id: int,
    branch: str,
    gitlab_token: str
) -> Dict[str, str]:
    """Fetch Dockerfile and .gitlab-ci.yml from a GitLab repo."""
    import httpx

    files = {"dockerfile": "", "gitlab_ci": ""}
    file_map = {
        "Dockerfile": "dockerfile",
        ".gitlab-ci.yml": "gitlab_ci"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"PRIVATE-TOKEN": gitlab_token}
        for filename, key in file_map.items():
            try:
                resp = await client.get(
                    f"http://gitlab-server/api/v4/projects/{project_id}/repository/files/{filename}/raw",
                    headers=headers,
                    params={"ref": branch}
                )
                if resp.status_code == 200:
                    files[key] = resp.text
            except Exception as e:
                print(f"[RL Background] Could not fetch {filename}: {e}")

    return files


async def _check_all_jobs_passed(project_id: int, pipeline_id: int, gitlab_token: str) -> bool:
    """Check if ALL pipeline jobs passed (no failures/skips except notify_failure)."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"http://gitlab-server/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs",
                headers={"PRIVATE-TOKEN": gitlab_token}
            )
            if resp.status_code != 200:
                return False
            jobs = resp.json()
            for job in jobs:
                name = job.get('name', '')
                status = job.get('status', '')
                if name == 'notify_failure' and status == 'skipped':
                    continue
                if name == 'learn_record' and status in ('running', 'success'):
                    continue
                if status != 'success':
                    print(f"[RL Background] Job '{name}' has status '{status}' — not all passed")
                    return False
            return True
    except Exception as e:
        print(f"[RL Background] All-jobs check failed: {e}")
        return False


async def monitor_pipeline_for_learning(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    project_id: int,
    dockerfile: str = "",
    gitlab_ci: str = "",
    language: str = "unknown",
    framework: str = "generic",
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30
):
    """
    Background task to monitor pipeline status, record results for RL,
    and trigger self-healing on failure.
    """
    import httpx

    print(f"[RL Background] Starting pipeline monitor for {branch}")

    max_checks = (max_wait_minutes * 60) // check_interval_seconds
    pipeline_id = None

    for check_num in range(max_checks):
        try:
            if check_num > 0:
                await asyncio.sleep(check_interval_seconds)

            async with httpx.AsyncClient() as client:
                headers = {"PRIVATE-TOKEN": gitlab_token}

                pipelines_url = f"http://gitlab-server/api/v4/projects/{project_id}/pipelines"
                resp = await client.get(
                    pipelines_url,
                    headers=headers,
                    params={"ref": branch, "per_page": 1}
                )

                if resp.status_code != 200:
                    print(f"[RL Background] Failed to get pipelines: {resp.status_code}")
                    continue

                pipelines = resp.json()
                if not pipelines:
                    print(f"[RL Background] No pipeline found yet for {branch}")
                    continue

                pipeline = pipelines[0]
                pipeline_id = pipeline['id']
                status = pipeline['status']

                print(f"[RL Background] Pipeline {pipeline_id} status: {status}")
                progress_store.set_pipeline_id(project_id, branch, pipeline_id)
                progress_store.update(project_id, branch, "pipeline_running",
                    f"Pipeline #{pipeline_id} is {status}...")

                if status in ['success', 'failed', 'canceled', 'skipped']:
                    result = await pipeline_generator.record_pipeline_result(
                        repo_url=repo_url,
                        gitlab_token=gitlab_token,
                        branch=branch,
                        pipeline_id=pipeline_id
                    )
                    print(f"[RL Background] Pipeline {pipeline_id} completed with status '{status}'. RL result: {result.get('message', 'recorded')}")

                    if status == 'success':
                        # Check if ALL jobs truly passed (allow_failure jobs may have failed)
                        all_jobs_passed = await _check_all_jobs_passed(project_id, pipeline_id, gitlab_token)
                        if all_jobs_passed:
                            progress_store.complete(project_id, branch, "success",
                                f"Pipeline #{pipeline_id} succeeded — all stages passed!")
                            return
                        else:
                            print(f"[RL Background] Pipeline {pipeline_id} succeeded but has failing jobs — triggering self-healing...")
                            # Fall through to self-healing (same as 'failed')

                    if status in ['canceled', 'skipped']:
                        progress_store.complete(project_id, branch, "failed",
                            f"Pipeline #{pipeline_id} was {status}.")
                        return

                    if status in ['failed', 'success']:  # success with failing jobs also triggers healing
                        if status == 'failed':
                            print(f"[RL Background] Pipeline {pipeline_id} FAILED — triggering self-healing...")
                        progress_store.update(project_id, branch, "pipeline_failed",
                            f"Pipeline #{pipeline_id} has failing jobs. Starting self-healing (max 10 attempts)...")

                        if not dockerfile or not gitlab_ci:
                            fetched = await _fetch_pipeline_files(project_id, branch, gitlab_token)
                            dockerfile = dockerfile or fetched["dockerfile"]
                            gitlab_ci = gitlab_ci or fetched["gitlab_ci"]

                        if language == "unknown":
                            try:
                                analysis = await pipeline_generator.analyze_repository(repo_url, gitlab_token)
                                language = analysis.get('language', 'unknown')
                                framework = analysis.get('framework', 'generic')
                            except Exception:
                                pass

                        heal_result = await self_healing_workflow.fix_existing_pipeline(
                            repo_url=repo_url,
                            gitlab_token=gitlab_token,
                            project_id=project_id,
                            pipeline_id=pipeline_id,
                            branch=branch,
                            language=language,
                            framework=framework,
                            dockerfile=dockerfile,
                            gitlab_ci=gitlab_ci,
                            max_attempts=10
                        )

                        print(f"[RL Background] Self-healing result: {heal_result.status.value}")

                        if heal_result.status == WorkflowStatus.SUCCESS:
                            progress_store.complete(project_id, branch, "success",
                                f"Pipeline fixed after {heal_result.attempt} attempt(s)!")
                        else:
                            progress_store.complete(project_id, branch, "failed",
                                f"Self-healing failed after {heal_result.attempt} attempts. GitLab issue created for review.")

                    return

        except Exception as e:
            print(f"[RL Background] Error checking pipeline: {e}")

    print(f"[RL Background] Timeout waiting for pipeline on {branch} after {max_wait_minutes} minutes")
    progress_store.complete(project_id, branch, "failed",
        f"Timeout waiting for pipeline after {max_wait_minutes} minutes.")


async def run_self_heal_background(
    repo_url: str,
    gitlab_token: str,
    additional_context: str,
    auto_commit: bool,
    max_attempts: int
):
    """Background task for self-healing workflow"""
    print(f"[Background] Starting self-heal for {repo_url}")
    result = await self_healing_workflow.run(
        repo_url=repo_url,
        gitlab_token=gitlab_token,
        additional_context=additional_context,
        auto_commit=auto_commit,
        max_attempts=max_attempts
    )
    print(f"[Background] Self-heal completed: {result.status.value}")


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/analyze")
async def analyze_repository(repo_url: str, gitlab_token: str):
    """Analyze a GitLab repository to understand its structure."""
    try:
        analysis = await pipeline_generator.analyze_repository(repo_url, gitlab_token)
        return {"success": True, "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate", response_model=GeneratePipelineResponse)
async def generate_pipeline(request: GeneratePipelineRequest):
    """Generate .gitlab-ci.yml and Dockerfile for a repository."""
    try:
        result = await pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only
        )
        return GeneratePipelineResponse(
            success=True,
            gitlab_ci=result['gitlab_ci'],
            dockerfile=result['dockerfile'],
            analysis=result['analysis'],
            model_used=result['model_used'],
            feedback_used=result['feedback_used']
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-validated", response_model=GenerateWithValidationResponse)
async def generate_pipeline_with_validation(request: GenerateWithValidationRequest):
    """Generate pipeline with dry-run validation and automatic LLM-based fixing."""
    try:
        result = await pipeline_generator.generate_with_validation(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            model=request.model,
            max_fix_attempts=request.max_fix_attempts,
            store_on_success=request.store_on_success
        )
        return GenerateWithValidationResponse(
            success=True,
            gitlab_ci=result.get('gitlab_ci', ''),
            dockerfile=result.get('dockerfile', ''),
            analysis=result.get('analysis', {}),
            model_used=result.get('model_used', ''),
            feedback_used=result.get('feedback_used', 0),
            validation_passed=result.get('validation_passed', False),
            validation_skipped=result.get('validation_skipped'),
            validation_reason=result.get('validation_reason'),
            validation_results=result.get('validation_results'),
            validation_errors=result.get('validation_errors'),
            warnings=result.get('warnings'),
            fix_attempts=result.get('fix_attempts'),
            fix_history=result.get('fix_history')
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dry-run", response_model=DryRunResponse)
async def dry_run_validation(request: DryRunRequest):
    """Validate pipeline and Dockerfile without committing to GitLab."""
    try:
        results = await gitlab_dry_run_validator.validate_all(
            gitlab_ci=request.gitlab_ci,
            dockerfile=request.dockerfile,
            gitlab_token=request.gitlab_token,
            project_path=request.project_path
        )

        all_valid, summary = gitlab_dry_run_validator.get_validation_summary(results)

        all_errors = []
        all_warnings = []
        for check_name, result in results.items():
            all_errors.extend([f"[{check_name}] {e}" for e in result.errors])
            all_warnings.extend([f"[{check_name}] {w}" for w in result.warnings])

        return DryRunResponse(
            success=True,
            valid=all_valid,
            errors=all_errors,
            warnings=all_warnings,
            validation_results={k: v.to_dict() for k, v in results.items()},
            summary=summary
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit", response_model=CommitResponse)
async def commit_pipeline(request: CommitRequest, background_tasks: BackgroundTasks):
    """Commit generated pipeline files to GitLab and start monitoring."""
    try:
        branch_name = request.branch_name
        if not branch_name:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"feature/ai-pipeline-{timestamp}"

        files = {
            ".gitlab-ci.yml": request.gitlab_ci,
            "Dockerfile": request.dockerfile
        }

        result = await pipeline_generator.commit_to_gitlab(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            files=files,
            branch_name=branch_name,
            commit_message=request.commit_message
        )

        progress = progress_store.create(project_id=result['project_id'], branch=branch_name, max_attempts=10)
        progress.model_used = get_active_provider_name()

        background_tasks.add_task(
            monitor_pipeline_for_learning,
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=branch_name,
            project_id=result['project_id'],
            dockerfile=request.dockerfile,
            gitlab_ci=request.gitlab_ci
        )

        return CommitResponse(
            success=True,
            commit_id=result['commit_id'],
            branch=result['branch'],
            web_url=result.get('web_url'),
            project_id=result['project_id']
        )
    except Exception as e:
        logger.error(f"Pipeline commit failed: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        detail = str(e) or f"{type(e).__name__}: Request to GitLab timed out or failed"
        raise HTTPException(status_code=500, detail=detail)


@router.get("/progress/{project_id}/{branch:path}")
async def get_pipeline_progress(project_id: int, branch: str):
    """Get real-time progress of pipeline monitoring and self-healing."""
    progress = progress_store.get(project_id, branch)
    if not progress:
        return {"found": False, "message": "No monitoring in progress for this pipeline"}
    return {"found": True, **progress.to_dict()}


@router.post("/status")
async def get_pipeline_status(request: PipelineStatusRequest):
    """Get the status of the latest pipeline for a branch."""
    try:
        status = await pipeline_generator.get_pipeline_status(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=request.branch
        )
        return {"success": True, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def store_feedback(request: FeedbackRequest):
    """Store feedback from manual corrections for reinforcement learning."""
    try:
        differences = await pipeline_generator.compare_and_learn(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=request.branch,
            generated_files={
                ".gitlab-ci.yml": request.original_gitlab_ci,
                "Dockerfile": request.original_dockerfile
            }
        )

        gitlab_ci_diff = differences.get(".gitlab-ci.yml", {})
        dockerfile_diff = differences.get("Dockerfile", {})

        if gitlab_ci_diff.get("changed") or dockerfile_diff.get("changed"):
            analysis = await pipeline_generator.analyze_repository(
                request.repo_url,
                request.gitlab_token
            )

            success = await pipeline_generator.store_feedback(
                original_gitlab_ci=request.original_gitlab_ci,
                corrected_gitlab_ci=gitlab_ci_diff.get("corrected", request.original_gitlab_ci),
                original_dockerfile=request.original_dockerfile,
                corrected_dockerfile=dockerfile_diff.get("corrected", request.original_dockerfile),
                language=analysis['language'],
                framework=analysis['framework'],
                error_type=request.error_type,
                fix_description=request.fix_description
            )

            return {
                "success": success,
                "message": "Feedback stored for reinforcement learning",
                "changes_detected": {
                    "gitlab_ci": gitlab_ci_diff.get("changed", False),
                    "dockerfile": dockerfile_diff.get("changed", False)
                }
            }
        else:
            return {
                "success": True,
                "message": "No changes detected between original and current files",
                "changes_detected": {"gitlab_ci": False, "dockerfile": False}
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/history")
async def get_feedback_history(
    language: Optional[str] = None,
    framework: Optional[str] = None,
    limit: int = 10
):
    """Get stored feedback history for review."""
    try:
        feedback = await pipeline_generator.get_relevant_feedback(
            language=language or "",
            framework=framework or "",
            limit=limit
        )
        return {"success": True, "feedback": feedback, "count": len(feedback)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Reinforcement Learning Endpoints
# ============================================================================

@router.post("/learn/record")
async def record_pipeline_result(request: RecordPipelineResultRequest):
    """Record the result of a pipeline for reinforcement learning."""
    try:
        result = await pipeline_generator.record_pipeline_result(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=request.branch,
            pipeline_id=request.pipeline_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/successful")
async def get_successful_pipelines(
    language: str,
    framework: Optional[str] = None,
    limit: int = 5
):
    """Get successful pipeline configurations for a language/framework."""
    try:
        pipelines = await pipeline_generator.get_successful_pipelines(
            language=language,
            framework=framework or "",
            limit=limit
        )
        return {
            "success": True,
            "language": language,
            "framework": framework,
            "pipelines": pipelines,
            "count": len(pipelines)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/best")
async def get_best_config(language: str, framework: Optional[str] = None):
    """Get the best performing pipeline configuration for a language/framework."""
    try:
        config = await pipeline_generator.get_best_pipeline_config(
            language=language,
            framework=framework or ""
        )
        if config:
            return {
                "success": True,
                "language": language,
                "framework": framework,
                "config": config,
                "source": "reinforcement_learning"
            }
        else:
            return {
                "success": True,
                "language": language,
                "framework": framework,
                "config": None,
                "message": "No successful pipeline configurations found for this language/framework"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/store-template")
async def store_template(request: StoreTemplateRequest):
    """Manually store a proven pipeline configuration."""
    try:
        success = await pipeline_generator.store_manual_template(
            language=request.language,
            framework=request.framework,
            gitlab_ci=request.gitlab_ci,
            dockerfile=request.dockerfile,
            description=request.description
        )
        if success:
            return {
                "success": True,
                "message": f"Template stored successfully for {request.language}/{request.framework}",
                "language": request.language,
                "framework": request.framework
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to store template")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow")
async def full_workflow(request: FullWorkflowRequest, background_tasks: BackgroundTasks):
    """Complete workflow: Analyze -> Generate -> Commit -> Monitor"""
    try:
        result = await pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only
        )

        response = {
            "success": True,
            "generation": {
                "gitlab_ci": result['gitlab_ci'],
                "dockerfile": result['dockerfile'],
                "analysis": result['analysis'],
                "model_used": result['model_used'],
                "feedback_used": result['feedback_used']
            },
            "commit": None,
            "pipeline": None
        }

        if request.auto_commit:
            branch_name = request.branch_name
            if not branch_name:
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                branch_name = f"feature/ai-pipeline-{timestamp}"

            files = {
                ".gitlab-ci.yml": result['gitlab_ci'],
                "Dockerfile": result['dockerfile']
            }

            model_used = result.get('model_used', 'unknown')
            if model_used == 'chromadb-direct':
                commit_tag = "RAG Template"
            elif 'chromadb' in model_used:
                commit_tag = "RAG + LLM"
            else:
                commit_tag = "AI Generated"

            commit_result = await pipeline_generator.commit_to_gitlab(
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                files=files,
                branch_name=branch_name,
                commit_message=f"Add CI/CD pipeline configuration [{commit_tag}]"
            )

            response["commit"] = {
                "branch": commit_result['branch'],
                "commit_id": commit_result['commit_id'],
                "web_url": commit_result.get('web_url'),
                "project_id": commit_result['project_id']
            }

            background_tasks.add_task(
                monitor_pipeline_for_learning,
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                branch=branch_name,
                project_id=commit_result['project_id'],
                dockerfile=result['dockerfile'],
                gitlab_ci=result['gitlab_ci'],
                language=result.get('analysis', {}).get('language', 'unknown'),
                framework=result.get('analysis', {}).get('framework', 'generic'),
                max_wait_minutes=15,
                check_interval_seconds=30
            )

            response["pipeline"] = {
                "message": "Pipeline triggered. RL + self-healing enabled - failures will be auto-fixed by LLM.",
                "branch": branch_name,
                "rl_enabled": True,
                "self_healing_enabled": True
            }

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Self-Healing Pipeline Endpoints
# ============================================================================

@router.post("/self-heal")
async def self_heal_pipeline(request: SelfHealRequest, background_tasks: BackgroundTasks):
    """Self-healing pipeline workflow with auto-fix and retry."""
    try:
        result = await self_healing_workflow.run(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            auto_commit=request.auto_commit,
            max_attempts=request.max_attempts
        )

        return {
            "success": result.status == WorkflowStatus.SUCCESS,
            "status": result.status.value,
            "language": result.language,
            "framework": result.framework,
            "branch": result.branch,
            "pipeline_id": result.pipeline_id,
            "template_source": result.template_source,
            "attempts": result.attempt,
            "errors": result.errors,
            "logs": result.logs,
            "files": {
                "dockerfile": result.dockerfile,
                "gitlab_ci": result.gitlab_ci
            } if result.dockerfile or result.gitlab_ci else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal/async")
async def self_heal_pipeline_async(request: SelfHealRequest, background_tasks: BackgroundTasks):
    """Self-healing pipeline (async) - runs in background."""
    try:
        background_tasks.add_task(
            run_self_heal_background,
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            auto_commit=request.auto_commit,
            max_attempts=request.max_attempts
        )

        return {
            "success": True,
            "message": "Self-healing workflow started in background",
            "repo_url": request.repo_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix")
async def fix_pipeline_error(request: FixRequest):
    """LLM Fix - Analyze error and generate fix."""
    try:
        result = await llm_fixer.generate_fix(
            dockerfile=request.dockerfile,
            gitlab_ci=request.gitlab_ci,
            error_log=request.error_log,
            job_name=request.job_name,
            language=request.language,
            framework=request.framework
        )

        return {
            "success": result.success,
            "error_identified": result.error_identified,
            "fix_applied": result.fix_applied,
            "explanation": result.explanation,
            "fixed_files": {
                "dockerfile": result.dockerfile,
                "gitlab_ci": result.gitlab_ci
            } if result.success else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix/from-job")
async def fix_from_gitlab_job(request: FixFromJobRequest):
    """LLM Fix from Job - Fetch error log and generate fix."""
    try:
        result = await llm_fixer.fix_from_job_log(
            dockerfile=request.dockerfile,
            gitlab_ci=request.gitlab_ci,
            job_id=request.job_id,
            project_id=request.project_id,
            gitlab_token=request.gitlab_token,
            language=request.language,
            framework=request.framework
        )

        return {
            "success": result.success,
            "error_identified": result.error_identified,
            "fix_applied": result.fix_applied,
            "explanation": result.explanation,
            "fixed_files": {
                "dockerfile": result.dockerfile,
                "gitlab_ci": result.gitlab_ci
            } if result.success else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
