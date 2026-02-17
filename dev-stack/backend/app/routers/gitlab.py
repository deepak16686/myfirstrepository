"""
GitLab API router
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any

from app.config import tools_manager
from app.integrations.gitlab import GitLabIntegration
from app.models.schemas import (
    GitLabProject, GitLabPipeline, GitLabJob, GitLabTriggerPipeline, APIResponse
)

router = APIRouter(prefix="/gitlab", tags=["GitLab"])


def get_gitlab() -> GitLabIntegration:
    config = tools_manager.get_tool("gitlab")
    if not config or not config.enabled:
        raise HTTPException(status_code=503, detail="GitLab integration not configured or disabled")
    return GitLabIntegration(config)


# ============================================================================
# Projects
# ============================================================================

@router.get("/projects", response_model=List[GitLabProject])
async def list_projects(
    search: Optional[str] = None,
    visibility: Optional[str] = None,
    per_page: int = Query(default=20, le=100),
    page: int = Query(default=1, ge=1)
):
    """List GitLab projects"""
    gitlab = get_gitlab()
    try:
        return await gitlab.list_projects(search, visibility, per_page, page)
    finally:
        await gitlab.close()


@router.get("/projects/{project_id}", response_model=GitLabProject)
async def get_project(project_id: int):
    """Get a specific project"""
    gitlab = get_gitlab()
    try:
        return await gitlab.get_project(project_id)
    finally:
        await gitlab.close()


@router.post("/projects", response_model=GitLabProject)
async def create_project(
    name: str,
    description: Optional[str] = None,
    visibility: str = "private"
):
    """Create a new project"""
    gitlab = get_gitlab()
    try:
        return await gitlab.create_project(name, description, visibility)
    finally:
        await gitlab.close()


# ============================================================================
# Pipelines
# ============================================================================

@router.get("/projects/{project_id}/pipelines", response_model=List[GitLabPipeline])
async def list_pipelines(
    project_id: int,
    status: Optional[str] = None,
    ref: Optional[str] = None,
    per_page: int = Query(default=20, le=100)
):
    """List pipelines for a project"""
    gitlab = get_gitlab()
    try:
        return await gitlab.list_pipelines(project_id, status, ref, per_page)
    finally:
        await gitlab.close()


@router.get("/projects/{project_id}/pipelines/{pipeline_id}", response_model=GitLabPipeline)
async def get_pipeline(project_id: int, pipeline_id: int):
    """Get a specific pipeline"""
    gitlab = get_gitlab()
    try:
        return await gitlab.get_pipeline(project_id, pipeline_id)
    finally:
        await gitlab.close()


@router.post("/projects/{project_id}/pipelines", response_model=GitLabPipeline)
async def trigger_pipeline(project_id: int, trigger: GitLabTriggerPipeline):
    """Trigger a new pipeline"""
    gitlab = get_gitlab()
    try:
        return await gitlab.trigger_pipeline(project_id, trigger.ref, trigger.variables)
    finally:
        await gitlab.close()


@router.post("/projects/{project_id}/pipelines/{pipeline_id}/cancel", response_model=GitLabPipeline)
async def cancel_pipeline(project_id: int, pipeline_id: int):
    """Cancel a running pipeline"""
    gitlab = get_gitlab()
    try:
        return await gitlab.cancel_pipeline(project_id, pipeline_id)
    finally:
        await gitlab.close()


@router.post("/projects/{project_id}/pipelines/{pipeline_id}/retry", response_model=GitLabPipeline)
async def retry_pipeline(project_id: int, pipeline_id: int):
    """Retry a failed pipeline"""
    gitlab = get_gitlab()
    try:
        return await gitlab.retry_pipeline(project_id, pipeline_id)
    finally:
        await gitlab.close()


# ============================================================================
# Jobs
# ============================================================================

@router.get("/projects/{project_id}/pipelines/{pipeline_id}/jobs", response_model=List[GitLabJob])
async def list_pipeline_jobs(project_id: int, pipeline_id: int):
    """List jobs in a pipeline"""
    gitlab = get_gitlab()
    try:
        return await gitlab.list_pipeline_jobs(project_id, pipeline_id)
    finally:
        await gitlab.close()


@router.get("/projects/{project_id}/jobs/{job_id}/log")
async def get_job_log(project_id: int, job_id: int):
    """Get job log output"""
    gitlab = get_gitlab()
    try:
        log = await gitlab.get_job_log(project_id, job_id)
        return {"log": log}
    finally:
        await gitlab.close()


@router.post("/projects/{project_id}/jobs/{job_id}/retry", response_model=GitLabJob)
async def retry_job(project_id: int, job_id: int):
    """Retry a failed job"""
    gitlab = get_gitlab()
    try:
        return await gitlab.retry_job(project_id, job_id)
    finally:
        await gitlab.close()


# ============================================================================
# Branches & Commits
# ============================================================================

@router.get("/projects/{project_id}/branches")
async def list_branches(project_id: int):
    """List branches in a project"""
    gitlab = get_gitlab()
    try:
        return await gitlab.list_branches(project_id)
    finally:
        await gitlab.close()


@router.get("/projects/{project_id}/commits")
async def list_commits(
    project_id: int,
    ref: str = "main",
    per_page: int = Query(default=20, le=100)
):
    """List commits in a project"""
    gitlab = get_gitlab()
    try:
        return await gitlab.list_commits(project_id, ref, per_page)
    finally:
        await gitlab.close()


# ============================================================================
# Merge Requests
# ============================================================================

@router.get("/projects/{project_id}/merge_requests")
async def list_merge_requests(
    project_id: int,
    state: str = "opened",
    per_page: int = Query(default=20, le=100)
):
    """List merge requests"""
    gitlab = get_gitlab()
    try:
        return await gitlab.list_merge_requests(project_id, state, per_page)
    finally:
        await gitlab.close()


@router.post("/projects/{project_id}/merge_requests")
async def create_merge_request(
    project_id: int,
    source_branch: str,
    target_branch: str,
    title: str,
    description: Optional[str] = None
):
    """Create a merge request"""
    gitlab = get_gitlab()
    try:
        return await gitlab.create_merge_request(
            project_id, source_branch, target_branch, title, description
        )
    finally:
        await gitlab.close()
