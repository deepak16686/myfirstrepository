"""
Pipeline Generator API Router

Provides endpoints for:
1. Generating GitLab CI/CD pipelines and Dockerfiles
2. Committing to GitLab repositories
3. Monitoring pipeline status
4. Storing and retrieving feedback for reinforcement learning
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.services.pipeline_generator import pipeline_generator

router = APIRouter(prefix="/pipeline", tags=["Pipeline Generator"])


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
        default="qwen2.5-coder:32b-instruct-q4_K_M",
        description="Ollama model to use for generation"
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
    model: str = "qwen2.5-coder:32b-instruct-q4_K_M"
    auto_commit: bool = True
    branch_name: Optional[str] = None


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
            model=request.model
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
            model=request.model
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

            # Note: Pipeline status check can be done separately
            # as it takes time for the pipeline to start
            response["pipeline"] = {
                "message": "Pipeline triggered. Use /pipeline/status to monitor progress.",
                "branch": branch_name
            }

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
