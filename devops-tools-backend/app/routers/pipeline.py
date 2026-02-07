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
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.services.pipeline_generator import pipeline_generator
from app.services.gitlab_dry_run_validator import gitlab_dry_run_validator
from app.services.self_healing_workflow import self_healing_workflow

router = APIRouter(prefix="/pipeline", tags=["Pipeline Generator"])


# ============================================================================
# Helper: Fetch Pipeline Files from GitLab
# ============================================================================

async def _fetch_pipeline_files(
    project_id: int,
    branch: str,
    gitlab_token: str
) -> Dict[str, str]:
    """
    Fetch Dockerfile and .gitlab-ci.yml from a GitLab repo.
    Used as fallback when file content is not passed directly.
    """
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


# ============================================================================
# Background Task for Reinforcement Learning + Self-Healing
# ============================================================================

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

    This task:
    1. Waits for the pipeline to start
    2. Monitors until completion or timeout
    3. Records the result (success/failure) in ChromaDB for learning
    4. If failed, triggers LLM-based auto-fix (max 3 retries)

    Args:
        repo_url: GitLab repository URL
        gitlab_token: GitLab access token
        branch: Branch name where pipeline is running
        project_id: GitLab project ID
        dockerfile: Current Dockerfile content (optional, fetched if empty)
        gitlab_ci: Current .gitlab-ci.yml content (optional, fetched if empty)
        language: Detected language (for self-healing context)
        framework: Detected framework (for self-healing context)
        max_wait_minutes: Maximum time to wait for pipeline completion
        check_interval_seconds: Time between status checks
    """
    import httpx

    print(f"[RL Background] Starting pipeline monitor for {branch}")

    max_checks = (max_wait_minutes * 60) // check_interval_seconds
    pipeline_id = None

    for check_num in range(max_checks):
        try:
            # Wait before checking (except first check)
            if check_num > 0:
                await asyncio.sleep(check_interval_seconds)

            async with httpx.AsyncClient() as client:
                headers = {"PRIVATE-TOKEN": gitlab_token}

                # Get latest pipeline for branch
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

                # Check if pipeline is complete
                if status in ['success', 'failed', 'canceled', 'skipped']:
                    # Record the result for RL
                    result = await pipeline_generator.record_pipeline_result(
                        repo_url=repo_url,
                        gitlab_token=gitlab_token,
                        branch=branch,
                        pipeline_id=pipeline_id
                    )
                    print(f"[RL Background] Pipeline {pipeline_id} completed with status '{status}'. RL result: {result.get('message', 'recorded')}")

                    # ══════════════════════════════════════════════════
                    # SELF-HEALING: Auto-fix failed pipelines via LLM
                    # ══════════════════════════════════════════════════
                    if status == 'failed':
                        print(f"[RL Background] Pipeline {pipeline_id} FAILED — triggering self-healing...")

                        # Fetch files from GitLab if not provided
                        if not dockerfile or not gitlab_ci:
                            fetched = await _fetch_pipeline_files(project_id, branch, gitlab_token)
                            dockerfile = dockerfile or fetched["dockerfile"]
                            gitlab_ci = gitlab_ci or fetched["gitlab_ci"]

                        # Detect language if unknown
                        if language == "unknown":
                            try:
                                analysis = await pipeline_generator.analyze_repository(repo_url, gitlab_token)
                                language = analysis.get('language', 'unknown')
                                framework = analysis.get('framework', 'generic')
                            except Exception:
                                pass

                        # Trigger self-healing (uses internal _monitor_pipeline, no recursion)
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
                            max_attempts=3
                        )

                        print(f"[RL Background] Self-healing result: {heal_result.status.value}")

                    return

        except Exception as e:
            print(f"[RL Background] Error checking pipeline: {e}")

    print(f"[RL Background] Timeout waiting for pipeline on {branch} after {max_wait_minutes} minutes")


# ============================================================================
# Request/Response Models
# ============================================================================

class GeneratePipelineRequest(BaseModel):
    """Request to generate pipeline files"""
    repo_url: str = Field(..., description="GitLab repository URL")
    gitlab_token: str = Field(..., description="GitLab access token")
    additional_context: Optional[str] = Field(
        None,
        description="Additional requirements or context for generation"
    )
    model: str = Field(
        default="pipeline-generator-v5",
        description="Ollama model to use for generation"
    )
    use_template_only: bool = Field(
        default=False,
        description="If True, skip LLM and use default templates directly"
    )


class GeneratePipelineResponse(BaseModel):
    """Response with generated pipeline files"""
    success: bool
    gitlab_ci: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int


class GenerateWithValidationRequest(BaseModel):
    """Request to generate pipeline with dry-run validation and auto-fixing"""
    repo_url: str = Field(..., description="GitLab repository URL")
    gitlab_token: str = Field(..., description="GitLab access token")
    additional_context: Optional[str] = Field(
        None,
        description="Additional requirements or context for generation"
    )
    model: str = Field(
        default="pipeline-generator-v5",
        description="Ollama model to use for generation"
    )
    max_fix_attempts: int = Field(
        default=3,
        description="Maximum number of LLM fix attempts if validation fails"
    )
    store_on_success: bool = Field(
        default=True,
        description="Store successful templates in ChromaDB for future use"
    )


class GenerateWithValidationResponse(BaseModel):
    """Response with validated pipeline files"""
    success: bool
    gitlab_ci: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int
    validation_passed: bool
    validation_skipped: Optional[bool] = None
    validation_reason: Optional[str] = None
    validation_results: Optional[Dict[str, Any]] = None
    validation_errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    fix_attempts: Optional[int] = None
    fix_history: Optional[List[Dict[str, Any]]] = None


class CommitRequest(BaseModel):
    """Request to commit files to GitLab"""
    repo_url: str
    gitlab_token: str
    gitlab_ci: str
    dockerfile: str
    branch_name: Optional[str] = Field(
        None,
        description="Branch name (auto-generated if not provided)"
    )
    commit_message: str = Field(
        default="Add CI/CD pipeline configuration [AI Generated]"
    )


class CommitResponse(BaseModel):
    """Response from commit operation"""
    success: bool
    commit_id: str
    branch: str
    web_url: Optional[str]
    project_id: int


class PipelineStatusRequest(BaseModel):
    """Request to get pipeline status"""
    repo_url: str
    gitlab_token: str
    branch: str


class DryRunRequest(BaseModel):
    """Request to validate pipeline without committing"""
    gitlab_ci: str = Field(..., description="Pipeline YAML to validate")
    dockerfile: str = Field(..., description="Dockerfile to validate")
    gitlab_token: Optional[str] = Field(None, description="GitLab token for CI lint API (optional)")
    project_path: Optional[str] = Field(None, description="Project path for project-specific lint (optional)")


class DryRunResponse(BaseModel):
    """Response with validation results"""
    success: bool
    valid: bool
    errors: List[str]
    warnings: List[str]
    validation_results: Dict[str, Any]
    summary: str


class FeedbackRequest(BaseModel):
    """Request to store feedback for reinforcement learning"""
    repo_url: str
    gitlab_token: str
    branch: str
    original_gitlab_ci: str
    original_dockerfile: str
    error_type: str = Field(..., description="Type of error that was fixed")
    fix_description: str = Field(..., description="Description of what was fixed")


class FullWorkflowRequest(BaseModel):
    """Request for complete workflow: generate -> commit -> monitor"""
    repo_url: str
    gitlab_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    auto_commit: bool = False  # Default to False - require user approval
    branch_name: Optional[str] = None
    use_template_only: bool = Field(
        default=False,
        description="If True, skip LLM and use default templates directly"
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/analyze")
async def analyze_repository(
    repo_url: str,
    gitlab_token: str
):
    """
    Analyze a GitLab repository to understand its structure.
    Returns detected language, framework, and existing files.
    """
    try:
        analysis = await pipeline_generator.analyze_repository(repo_url, gitlab_token)
        return {"success": True, "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate", response_model=GeneratePipelineResponse)
async def generate_pipeline(request: GeneratePipelineRequest):
    """
    Generate .gitlab-ci.yml and Dockerfile for a repository.

    Uses Ollama to generate files based on:
    - Repository analysis (language, framework, files)
    - Previous feedback from reinforcement learning
    - Additional context provided by user
    """
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
    """
    Generate pipeline with dry-run validation and automatic LLM-based fixing.

    This endpoint:
    1. Checks ChromaDB for existing validated templates
    2. If no template exists, generates using LLM
    3. Validates using GitLab CI lint API and local checks
    4. If validation fails, uses LLM to fix errors (up to max_fix_attempts)
    5. Stores successful templates in ChromaDB for future use

    This is the recommended endpoint for generating pipelines for new/unknown
    languages and frameworks as it ensures the pipeline is valid before returning.
    """
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
    """
    Validate pipeline and Dockerfile without committing to GitLab.

    Performs:
    1. YAML syntax validation
    2. Dockerfile syntax validation
    3. Pipeline structure validation
    4. Stage dependency validation
    5. Nexus registry usage validation
    6. GitLab CI Lint API validation (if gitlab_token provided)

    This is useful for testing pipeline configurations before committing.
    """
    try:
        results = await gitlab_dry_run_validator.validate_all(
            gitlab_ci=request.gitlab_ci,
            dockerfile=request.dockerfile,
            gitlab_token=request.gitlab_token,
            project_path=request.project_path
        )

        all_valid, summary = gitlab_dry_run_validator.get_validation_summary(results)

        # Collect all errors and warnings
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
    """
    Commit generated pipeline files to GitLab.

    Creates a new branch and commits:
    - .gitlab-ci.yml
    - Dockerfile

    After commit, automatically monitors the pipeline and triggers
    LLM-based self-healing if the pipeline fails (max 3 retries).
    """
    try:
        # Generate branch name if not provided
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

        # Schedule background monitoring with self-healing
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status")
async def get_pipeline_status(request: PipelineStatusRequest):
    """
    Get the status of the latest pipeline for a branch.

    Returns:
    - Pipeline status (pending, running, success, failed, etc.)
    - Duration
    - Failed jobs (if any)
    """
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
    """
    Store feedback from manual corrections for reinforcement learning.

    Call this endpoint after a DevOps engineer has manually fixed
    the generated pipeline. The system will:
    1. Fetch the corrected files from the repository
    2. Compare with the original generated files
    3. Store the differences in ChromaDB for future learning
    """
    try:
        # Get corrected files from repo
        differences = await pipeline_generator.compare_and_learn(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=request.branch,
            generated_files={
                ".gitlab-ci.yml": request.original_gitlab_ci,
                "Dockerfile": request.original_dockerfile
            }
        )

        # Store feedback if there were changes
        gitlab_ci_diff = differences.get(".gitlab-ci.yml", {})
        dockerfile_diff = differences.get("Dockerfile", {})

        if gitlab_ci_diff.get("changed") or dockerfile_diff.get("changed"):
            # Get repository analysis for language/framework
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
    """
    Get stored feedback history for review.
    """
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

class RecordPipelineResultRequest(BaseModel):
    """Request to record pipeline result for RL"""
    repo_url: str
    gitlab_token: str
    branch: str
    pipeline_id: int


@router.post("/learn/record")
async def record_pipeline_result(request: RecordPipelineResultRequest):
    """
    Record the result of a pipeline for reinforcement learning.

    Call this endpoint after a pipeline completes (success or failure).
    - If successful: The configuration is stored in ChromaDB for future use
    - If failed: The failure pattern is recorded for analysis

    This enables the system to learn from real pipeline executions and
    improve future generations.
    """
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
    """
    Get successful pipeline configurations for a language/framework.

    Returns stored configurations that have been proven to work,
    sorted by performance (stages passed, duration).
    """
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
async def get_best_config(
    language: str,
    framework: Optional[str] = None
):
    """
    Get the best performing pipeline configuration for a language/framework.

    This returns the optimal configuration based on:
    - Number of stages that passed
    - Pipeline duration (faster is better)
    """
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


class StoreTemplateRequest(BaseModel):
    """Request to store a pipeline template manually"""
    language: str
    framework: str = "generic"
    gitlab_ci: str
    dockerfile: Optional[str] = None
    description: Optional[str] = None


@router.post("/learn/store-template")
async def store_template(request: StoreTemplateRequest):
    """
    Manually store a proven pipeline configuration.

    Use this to add a working pipeline configuration to the RL database
    so it can be used as a reference for future pipeline generation.
    """
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
    """
    Complete workflow: Analyze -> Generate -> Commit -> Monitor

    This endpoint:
    1. Analyzes the repository
    2. Generates .gitlab-ci.yml and Dockerfile
    3. Optionally commits to a new branch
    4. Returns all results with pipeline monitoring info

    Use this for the complete AI-powered pipeline generation flow.
    """
    try:
        # Step 1: Generate pipeline files
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

        # Step 2: Commit if requested
        if request.auto_commit:
            branch_name = request.branch_name
            if not branch_name:
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                branch_name = f"feature/ai-pipeline-{timestamp}"

            files = {
                ".gitlab-ci.yml": result['gitlab_ci'],
                "Dockerfile": result['dockerfile']
            }

            commit_result = await pipeline_generator.commit_to_gitlab(
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                files=files,
                branch_name=branch_name,
                commit_message="Add CI/CD pipeline configuration [AI Generated]"
            )

            response["commit"] = {
                "branch": commit_result['branch'],
                "commit_id": commit_result['commit_id'],
                "web_url": commit_result.get('web_url'),
                "project_id": commit_result['project_id']
            }

            # Schedule background task to monitor pipeline, record RL, and self-heal on failure
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
# SELF-HEALING PIPELINE ENDPOINTS
# ============================================================================

from app.services.dry_run_validator import dry_run_validator
from app.services.llm_fixer import llm_fixer
from app.services.self_healing_workflow import WorkflowStatus


class SelfHealRequest(BaseModel):
    """Request for self-healing pipeline workflow"""
    repo_url: str = Field(..., description="GitLab repository URL")
    gitlab_token: str = Field(..., description="GitLab access token")
    additional_context: Optional[str] = Field(
        None,
        description="Additional context for LLM generation"
    )
    auto_commit: bool = Field(
        default=True,
        description="Automatically commit and run pipeline"
    )
    max_attempts: int = Field(
        default=3,
        description="Maximum fix attempts before giving up"
    )


class DryRunRequest(BaseModel):
    """Request for dry-run validation"""
    gitlab_ci: str = Field(..., description=".gitlab-ci.yml content")
    dockerfile: str = Field(..., description="Dockerfile content")
    gitlab_token: Optional[str] = Field(None, description="GitLab token for lint API")


class FixRequest(BaseModel):
    """Request for LLM fix"""
    dockerfile: str
    gitlab_ci: str
    error_log: str = Field(..., description="Error log from failed job")
    job_name: str = Field(default="unknown", description="Name of failed job")
    language: str = Field(default="unknown")
    framework: str = Field(default="generic")


class FixFromJobRequest(BaseModel):
    """Request to fix from GitLab job ID"""
    dockerfile: str
    gitlab_ci: str
    job_id: int
    project_id: int
    gitlab_token: str
    language: str = "unknown"
    framework: str = "generic"


@router.post("/self-heal")
async def self_heal_pipeline(request: SelfHealRequest, background_tasks: BackgroundTasks):
    """
    🔄 SELF-HEALING PIPELINE WORKFLOW

    Complete automated workflow that:
    1. Checks ChromaDB for existing templates
    2. Generates new template via LLM if not found
    3. Validates with dry-run before committing
    4. Auto-fixes validation errors via LLM
    5. Commits to GitLab and monitors pipeline
    6. Auto-fixes failed pipelines via LLM (max 3 retries)
    7. Stores successful templates in ChromaDB

    This endpoint runs the full workflow synchronously.
    For async execution, use /self-heal/async.
    """
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


@router.post("/self-heal/async")
async def self_heal_pipeline_async(request: SelfHealRequest, background_tasks: BackgroundTasks):
    """
    🔄 SELF-HEALING PIPELINE (ASYNC)

    Same as /self-heal but runs in the background.
    Returns immediately with a tracking ID.
    """
    try:
        # Add to background tasks
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


@router.post("/dry-run")
async def dry_run_validation(request: DryRunRequest):
    """
    🧪 DRY-RUN VALIDATION

    Validates Dockerfile and .gitlab-ci.yml BEFORE committing:
    - YAML syntax validation
    - Dockerfile syntax validation
    - GitLab CI structure validation
    - GitLab CI Lint API validation
    - Nexus image availability check

    Use this to catch errors before running the actual pipeline.
    """
    try:
        results = await dry_run_validator.validate_all(
            gitlab_ci=request.gitlab_ci,
            dockerfile=request.dockerfile,
            gitlab_token=request.gitlab_token
        )

        all_valid, summary = dry_run_validator.get_validation_summary(results)

        return {
            "valid": all_valid,
            "summary": summary,
            "checks": {name: result.to_dict() for name, result in results.items()}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix")
async def fix_pipeline_error(request: FixRequest):
    """
    🔧 LLM FIX - Analyze Error and Generate Fix

    Sends the error log to LLM which:
    1. Analyzes the error pattern
    2. Identifies the root cause
    3. Generates fixed Dockerfile and .gitlab-ci.yml

    Use this after a pipeline fails to get AI-generated fixes.
    """
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
    """
    🔧 LLM FIX FROM JOB - Fetch Error Log and Generate Fix

    Fetches the error log from a failed GitLab job and generates a fix.
    Useful when you have a job ID but not the error log.
    """
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
