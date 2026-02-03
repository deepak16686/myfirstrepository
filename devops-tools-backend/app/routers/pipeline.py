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

router = APIRouter(prefix="/pipeline", tags=["Pipeline Generator"])


# ============================================================================
# Background Task for Reinforcement Learning
# ============================================================================

async def monitor_pipeline_for_learning(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    project_id: int,
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30
):
    """
    Background task to monitor pipeline status and record results for RL.

    This task:
    1. Waits for the pipeline to start
    2. Monitors until completion or timeout
    3. Records the result (success/failure) in ChromaDB for learning

    Args:
        repo_url: GitLab repository URL
        gitlab_token: GitLab access token
        branch: Branch name where pipeline is running
        project_id: GitLab project ID
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
                    # Record the result
                    result = await pipeline_generator.record_pipeline_result(
                        repo_url=repo_url,
                        gitlab_token=gitlab_token,
                        branch=branch,
                        pipeline_id=pipeline_id
                    )
                    print(f"[RL Background] Pipeline {pipeline_id} completed with status '{status}'. RL result: {result.get('message', 'recorded')}")
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
        default="pipeline-generator-v4",
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
    model: str = "pipeline-generator-v4"
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


@router.post("/commit", response_model=CommitResponse)
async def commit_pipeline(request: CommitRequest):
    """
    Commit generated pipeline files to GitLab.

    Creates a new branch and commits:
    - .gitlab-ci.yml
    - Dockerfile
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

            # Schedule background task to monitor pipeline and record result for RL
            background_tasks.add_task(
                monitor_pipeline_for_learning,
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                branch=branch_name,
                project_id=commit_result['project_id'],
                max_wait_minutes=15,
                check_interval_seconds=30
            )

            response["pipeline"] = {
                "message": "Pipeline triggered. Reinforcement learning enabled - results will be recorded automatically.",
                "branch": branch_name,
                "rl_enabled": True
            }

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
