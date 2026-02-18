"""
File: compliance_checker.py
Purpose: Aggregates SonarQube quality-gate statuses and Trivy container-image vulnerability scans
    into a unified per-project compliance report and a multi-project dashboard, with the ability
    to auto-discover matching Docker images in Nexus.
When Used: Invoked by the frontend Compliance Checker tool card when a user requests a compliance
    report for a single project or views the full compliance dashboard across all SonarQube
    projects via the /compliance/* routes.
Why Created: Combines data from three separate tools (SonarQube, Trivy, Nexus) into a single
    compliance view, avoiding the need for the frontend to orchestrate multiple API calls and
    merge the results itself.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.compliance_checker import compliance_checker_service

router = APIRouter(prefix="/compliance", tags=["Compliance Checker"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ProjectComplianceRequest(BaseModel):
    project_key: str
    docker_image: Optional[str] = None
    trivy_severity: str = "HIGH,CRITICAL"


class DashboardRequest(BaseModel):
    search: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/projects")
async def list_projects(search: Optional[str] = None):
    """List SonarQube projects with quality gate status."""
    try:
        result = await compliance_checker_service.list_projects(search=search)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project/compliance")
async def get_project_compliance(request: ProjectComplianceRequest):
    """Get full compliance report for a single project."""
    try:
        result = await compliance_checker_service.get_project_compliance(
            project_key=request.project_key,
            docker_image=request.docker_image,
            trivy_severity=request.trivy_severity,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/project/{project_key}/images")
async def find_docker_images(project_key: str):
    """Find Docker images in Nexus matching a project key."""
    try:
        result = await compliance_checker_service.find_docker_images(project_key)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard")
async def get_dashboard(request: DashboardRequest):
    """Get full compliance dashboard with all projects."""
    try:
        result = await compliance_checker_service.get_dashboard(search=request.search)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
