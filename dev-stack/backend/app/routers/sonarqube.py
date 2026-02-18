"""
File: sonarqube.py
Purpose: Exposes a comprehensive REST proxy to the SonarQube API, covering project management,
    quality-gate status, code metrics retrieval, issue listing by severity/type, analysis history,
    and a composite project summary endpoint.
When Used: Invoked by the frontend SonarQube tool card for browsing projects and quality data,
    and consumed internally by the compliance checker to aggregate quality-gate results via the
    /sonarqube/* routes.
Why Created: Wraps the SonarQubeIntegration client into a FastAPI router with Pydantic response
    models, keeping SonarQube-specific API details out of higher-level services like the
    compliance checker and pipeline generators.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any

from app.config import tools_manager
from app.integrations.sonarqube import SonarQubeIntegration
from app.models.schemas import (
    SonarQubeProject, SonarQubeMetric, SonarQubeQualityGate,
    SonarQubeIssue, APIResponse
)

router = APIRouter(prefix="/sonarqube", tags=["SonarQube"])


def get_sonarqube() -> SonarQubeIntegration:
    config = tools_manager.get_tool("sonarqube")
    if not config or not config.enabled:
        raise HTTPException(status_code=503, detail="SonarQube integration not configured or disabled")
    return SonarQubeIntegration(config)


# ============================================================================
# Projects
# ============================================================================

@router.get("/projects", response_model=List[SonarQubeProject])
async def list_projects(
    search: Optional[str] = None,
    page_size: int = Query(default=50, le=500),
    page: int = Query(default=1, ge=1)
):
    """List SonarQube projects"""
    sonar = get_sonarqube()
    try:
        return await sonar.list_projects(search, page_size, page)
    finally:
        await sonar.close()


@router.get("/projects/{project_key}", response_model=SonarQubeProject)
async def get_project(project_key: str):
    """Get a specific project"""
    sonar = get_sonarqube()
    try:
        project = await sonar.get_project(project_key)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_key}' not found")
        return project
    finally:
        await sonar.close()


@router.post("/projects", response_model=SonarQubeProject)
async def create_project(
    project_key: str,
    name: str,
    visibility: str = "private"
):
    """Create a new project"""
    sonar = get_sonarqube()
    try:
        return await sonar.create_project(project_key, name, visibility)
    finally:
        await sonar.close()


@router.delete("/projects/{project_key}", response_model=APIResponse)
async def delete_project(project_key: str):
    """Delete a project"""
    sonar = get_sonarqube()
    try:
        success = await sonar.delete_project(project_key)
        if success:
            return APIResponse(success=True, message=f"Project '{project_key}' deleted")
        raise HTTPException(status_code=500, detail="Failed to delete project")
    finally:
        await sonar.close()


# ============================================================================
# Quality Gates
# ============================================================================

@router.get("/projects/{project_key}/quality-gate", response_model=SonarQubeQualityGate)
async def get_quality_gate_status(project_key: str):
    """Get quality gate status for a project"""
    sonar = get_sonarqube()
    try:
        return await sonar.get_quality_gate_status(project_key)
    finally:
        await sonar.close()


@router.get("/quality-gates")
async def list_quality_gates():
    """List all quality gates"""
    sonar = get_sonarqube()
    try:
        return await sonar.list_quality_gates()
    finally:
        await sonar.close()


# ============================================================================
# Metrics
# ============================================================================

@router.get("/projects/{project_key}/metrics", response_model=List[SonarQubeMetric])
async def get_project_metrics(
    project_key: str,
    metrics: Optional[str] = None
):
    """
    Get metrics for a project.

    Args:
        project_key: Project key
        metrics: Comma-separated list of metrics (optional)
    """
    sonar = get_sonarqube()
    try:
        metric_list = metrics.split(",") if metrics else None
        return await sonar.get_metrics(project_key, metric_list)
    finally:
        await sonar.close()


# ============================================================================
# Issues
# ============================================================================

@router.get("/projects/{project_key}/issues", response_model=List[SonarQubeIssue])
async def list_issues(
    project_key: str,
    severities: Optional[str] = None,
    types: Optional[str] = None,
    statuses: str = "OPEN,CONFIRMED,REOPENED",
    page_size: int = Query(default=100, le=500),
    page: int = Query(default=1, ge=1)
):
    """
    List issues for a project.

    Args:
        project_key: Project key
        severities: Comma-separated severities (BLOCKER,CRITICAL,MAJOR,MINOR,INFO)
        types: Comma-separated types (BUG,VULNERABILITY,CODE_SMELL)
        statuses: Comma-separated statuses
    """
    sonar = get_sonarqube()
    try:
        return await sonar.list_issues(project_key, severities, types, statuses, page_size, page)
    finally:
        await sonar.close()


@router.get("/projects/{project_key}/issues/count")
async def get_issue_count(project_key: str):
    """Get issue counts by severity for a project"""
    sonar = get_sonarqube()
    try:
        return await sonar.get_issue_count(project_key)
    finally:
        await sonar.close()


# ============================================================================
# Analysis
# ============================================================================

@router.get("/projects/{project_key}/analyses")
async def get_analysis_history(
    project_key: str,
    page_size: int = Query(default=10, le=100)
):
    """Get analysis history for a project"""
    sonar = get_sonarqube()
    try:
        return await sonar.get_analysis_history(project_key, page_size)
    finally:
        await sonar.close()


# ============================================================================
# Summary Endpoint
# ============================================================================

@router.get("/projects/{project_key}/summary")
async def get_project_summary(project_key: str):
    """
    Get a comprehensive summary of a project including:
    - Project info
    - Quality gate status
    - Key metrics
    - Issue counts
    """
    sonar = get_sonarqube()
    try:
        project = await sonar.get_project(project_key)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_key}' not found")

        quality_gate = await sonar.get_quality_gate_status(project_key)
        metrics = await sonar.get_metrics(project_key)
        issue_counts = await sonar.get_issue_count(project_key)

        return {
            "project": project,
            "quality_gate": quality_gate,
            "metrics": {m.metric: m.value for m in metrics},
            "issues": issue_counts
        }
    finally:
        await sonar.close()
