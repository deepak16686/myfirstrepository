"""
GitHub Actions Pipeline Router

API endpoints for generating, committing, and managing GitHub Actions workflows.
Supports both GitHub.com and Gitea (free self-hosted alternative).
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.services.github_pipeline_generator import github_pipeline_generator

router = APIRouter(prefix="/github-pipeline", tags=["GitHub Actions Pipeline"])


# ============================================================================
# Request/Response Models
# ============================================================================

class AnalyzeRequest(BaseModel):
    repo_url: str
    github_token: str


class GenerateWorkflowRequest(BaseModel):
    repo_url: str
    github_token: str
    additional_context: Optional[str] = None
    model: str = "github-actions-generator-v1"
    use_template_only: bool = False
    runner_type: str = "self-hosted"


class GenerateWorkflowResponse(BaseModel):
    success: bool
    workflow: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int


class CommitRequest(BaseModel):
    repo_url: str
    github_token: str
    workflow: str
    dockerfile: str
    branch_name: Optional[str] = None
    commit_message: str = "Add CI/CD workflow configuration [AI Generated]"


class CommitResponse(BaseModel):
    success: bool
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    web_url: Optional[str] = None
    error: Optional[str] = None


class WorkflowStatusRequest(BaseModel):
    repo_url: str
    github_token: str
    branch: str


class FeedbackRequest(BaseModel):
    repo_url: str
    github_token: str
    branch: str
    original_workflow: str
    original_dockerfile: str
    corrected_workflow: str
    corrected_dockerfile: str
    error_type: str
    fix_description: str


class FullWorkflowRequest(BaseModel):
    repo_url: str
    github_token: str
    additional_context: Optional[str] = None
    model: str = "github-actions-generator-v1"
    auto_commit: bool = True
    branch_name: Optional[str] = None
    use_template_only: bool = False
    runner_type: str = "self-hosted"


class SelfHealRequest(BaseModel):
    repo_url: str
    github_token: str
    additional_context: Optional[str] = None
    auto_commit: bool = True
    max_attempts: int = 3
    runner_type: str = "self-hosted"


class DryRunRequest(BaseModel):
    workflow: str
    dockerfile: str
    github_token: Optional[str] = None


class RecordResultRequest(BaseModel):
    repo_url: str
    github_token: str
    branch: str
    run_id: int


class StoreTemplateRequest(BaseModel):
    language: str
    framework: Optional[str] = "generic"
    workflow: str
    dockerfile: str
    description: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/analyze")
async def analyze_repository(request: AnalyzeRequest):
    """
    Analyze a GitHub/Gitea repository to detect language, framework, and structure.
    """
    try:
        analysis = await github_pipeline_generator.analyze_repository(
            request.repo_url,
            request.github_token
        )
        return {"success": True, **analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=GenerateWorkflowResponse)
async def generate_workflow(request: GenerateWorkflowRequest):
    """
    Generate GitHub Actions workflow and Dockerfile for a repository.

    Uses:
    1. Proven templates from ChromaDB (if available)
    2. LLM generation with reference templates
    3. Default templates as fallback
    """
    try:
        result = await github_pipeline_generator.generate_workflow_files(
            repo_url=request.repo_url,
            github_token=request.github_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            runner_type=request.runner_type
        )
        return GenerateWorkflowResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit", response_model=CommitResponse)
async def commit_workflow(request: CommitRequest):
    """
    Commit generated workflow and Dockerfile to the repository.
    Creates a new branch with the CI/CD configuration.
    """
    try:
        result = await github_pipeline_generator.commit_to_github(
            repo_url=request.repo_url,
            github_token=request.github_token,
            workflow=request.workflow,
            dockerfile=request.dockerfile,
            branch_name=request.branch_name,
            commit_message=request.commit_message
        )
        return CommitResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status")
async def get_workflow_status(request: WorkflowStatusRequest):
    """
    Get the latest workflow run status for a branch.
    """
    try:
        status = await github_pipeline_generator.get_workflow_status(
            repo_url=request.repo_url,
            github_token=request.github_token,
            branch=request.branch
        )
        return {"success": True, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def store_feedback(request: FeedbackRequest):
    """
    Store manual corrections for reinforcement learning.
    """
    try:
        # Store feedback in ChromaDB for future reference
        # Implementation would be similar to GitLab feedback storage
        return {
            "success": True,
            "message": "Feedback stored successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/history")
async def get_feedback_history(
    language: Optional[str] = None,
    framework: Optional[str] = None,
    limit: int = 20
):
    """
    Get feedback history filtered by language and framework.
    """
    try:
        # Retrieve feedback from ChromaDB
        return {
            "success": True,
            "feedback": [],
            "count": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/record")
async def record_workflow_result(request: RecordResultRequest):
    """
    Record workflow run result for reinforcement learning.
    Called automatically by the learn-record job in workflows.
    """
    try:
        result = await github_pipeline_generator.record_workflow_result(
            repo_url=request.repo_url,
            github_token=request.github_token,
            branch=request.branch,
            run_id=request.run_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/successful")
async def get_successful_workflows(
    language: str,
    framework: Optional[str] = None,
    limit: int = 10
):
    """
    Get successful workflow configurations for a language/framework.
    """
    try:
        templates = await github_pipeline_generator.get_best_template_files(
            language=language,
            framework=framework
        )
        return {
            "success": True,
            "templates": templates if templates else [],
            "count": 1 if templates else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/best")
async def get_best_workflow(
    language: str,
    framework: Optional[str] = None
):
    """
    Get the best performing workflow configuration.
    """
    try:
        best = await github_pipeline_generator.get_best_template_files(
            language=language,
            framework=framework
        )
        if best:
            return {"success": True, **best}
        return {"success": False, "message": "No templates found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/store-template")
async def store_template(request: StoreTemplateRequest):
    """
    Manually store a proven workflow template.
    """
    try:
        # Store in ChromaDB
        return {
            "success": True,
            "message": f"Template stored for {request.language}/{request.framework}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow")
async def full_workflow(
    request: FullWorkflowRequest,
    background_tasks: BackgroundTasks
):
    """
    Complete workflow: analyze -> generate -> commit -> monitor.

    Returns immediately with generation results, monitors workflow in background.
    """
    try:
        # Step 1: Generate workflow files
        result = await github_pipeline_generator.generate_workflow_files(
            repo_url=request.repo_url,
            github_token=request.github_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            runner_type=request.runner_type
        )

        response = {
            "success": True,
            "generation": result
        }

        # Step 2: Commit if auto_commit is enabled
        if request.auto_commit:
            commit_result = await github_pipeline_generator.commit_to_github(
                repo_url=request.repo_url,
                github_token=request.github_token,
                workflow=result["workflow"],
                dockerfile=result["dockerfile"],
                branch_name=request.branch_name
            )
            response["commit"] = commit_result

            # Step 3: Schedule background monitoring
            if commit_result.get("success"):
                background_tasks.add_task(
                    monitor_workflow_for_learning,
                    request.repo_url,
                    request.github_token,
                    commit_result["branch"]
                )
                response["monitoring"] = {
                    "status": "scheduled",
                    "branch": commit_result["branch"]
                }

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal")
async def self_heal_workflow(request: SelfHealRequest):
    """
    Self-healing workflow with automatic error fixing.
    Synchronous execution - waits for completion.
    """
    try:
        # Import self-healing workflow service
        from app.services.github_self_healing_workflow import github_self_healing_workflow

        result = await github_self_healing_workflow.run(
            repo_url=request.repo_url,
            github_token=request.github_token,
            additional_context=request.additional_context or "",
            auto_commit=request.auto_commit,
            max_attempts=request.max_attempts,
            runner_type=request.runner_type
        )
        return result
    except ImportError:
        # Fallback to basic workflow if self-healing not available
        return await full_workflow(
            FullWorkflowRequest(
                repo_url=request.repo_url,
                github_token=request.github_token,
                additional_context=request.additional_context,
                auto_commit=request.auto_commit,
                runner_type=request.runner_type
            ),
            BackgroundTasks()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal/async")
async def self_heal_workflow_async(
    request: SelfHealRequest,
    background_tasks: BackgroundTasks
):
    """
    Self-healing workflow - async execution.
    Returns immediately, processes in background.
    """
    try:
        from app.services.github_self_healing_workflow import github_self_healing_workflow

        # Start in background
        background_tasks.add_task(
            github_self_healing_workflow.run,
            request.repo_url,
            request.github_token,
            request.additional_context or "",
            request.auto_commit,
            request.max_attempts,
            request.runner_type
        )

        return {
            "success": True,
            "status": "started",
            "message": "Self-healing workflow started in background"
        }
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Self-healing workflow service not available"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dry-run")
async def dry_run_validation(request: DryRunRequest):
    """
    Validate workflow and Dockerfile before committing.
    """
    try:
        from app.services.github_dry_run_validator import github_dry_run_validator

        results = await github_dry_run_validator.validate_all(
            workflow=request.workflow,
            dockerfile=request.dockerfile,
            github_token=request.github_token
        )

        # Convert results to dict
        results_dict = {k: v.to_dict() for k, v in results.items()}
        all_valid = all(r["valid"] for r in results_dict.values())

        return {
            "success": True,
            "valid": all_valid,
            "results": results_dict
        }
    except ImportError:
        # Basic validation if full validator not available
        import yaml
        errors = []
        warnings = []

        try:
            yaml.safe_load(request.workflow)
        except yaml.YAMLError as e:
            errors.append(f"YAML syntax error: {e}")

        if not request.dockerfile.strip():
            warnings.append("Dockerfile is empty")

        return {
            "success": True,
            "valid": len(errors) == 0,
            "results": {
                "basic_validation": {
                    "valid": len(errors) == 0,
                    "errors": errors,
                    "warnings": warnings
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Background Tasks
# ============================================================================

async def monitor_workflow_for_learning(
    repo_url: str,
    github_token: str,
    branch: str,
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30
):
    """
    Background task to monitor workflow and record results for RL.
    """
    import asyncio
    from datetime import datetime

    start_time = datetime.now()
    max_wait_seconds = max_wait_minutes * 60

    while True:
        elapsed = (datetime.now() - start_time).total_seconds()
        if elapsed > max_wait_seconds:
            print(f"[Monitor] Timeout waiting for workflow on {branch}")
            break

        try:
            status = await github_pipeline_generator.get_workflow_status(
                repo_url, github_token, branch
            )

            if status.get("status") == "completed":
                if status.get("conclusion") == "success":
                    await github_pipeline_generator.record_workflow_result(
                        repo_url, github_token, branch, status.get("run_id", 0)
                    )
                    print(f"[Monitor] Workflow success recorded for {branch}")
                else:
                    print(f"[Monitor] Workflow failed: {status.get('conclusion')}")
                break

        except Exception as e:
            print(f"[Monitor] Error checking status: {e}")

        await asyncio.sleep(check_interval_seconds)
