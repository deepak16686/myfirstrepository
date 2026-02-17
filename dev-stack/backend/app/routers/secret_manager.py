"""
Secret Manager Router

Endpoints for managing secrets across GitLab, Gitea, and Jenkins.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.secret_manager import secret_manager_service

router = APIRouter(prefix="/secret-manager", tags=["Secret Manager"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateSecretRequest(BaseModel):
    platform: str          # "gitlab" | "gitea" | "jenkins"
    scope: str             # "project:123", "org:jenkins-projects", "system"
    key: str
    value: str
    protected: bool = False
    masked: bool = False
    environment_scope: str = "*"
    description: str = ""


class UpdateSecretRequest(BaseModel):
    platform: str
    scope: str
    key: str
    value: str
    protected: bool = False
    masked: bool = False
    environment_scope: str = "*"
    description: str = ""


class DeleteSecretRequest(BaseModel):
    platform: str
    scope: str
    key: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/list")
async def list_all_secrets():
    """List secrets from all platforms."""
    try:
        result = await secret_manager_service.list_all()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gitlab/projects")
async def list_gitlab_projects():
    """List GitLab projects for the secret creation dropdown."""
    try:
        result = await secret_manager_service.list_gitlab_projects()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_secret(request: CreateSecretRequest):
    """Create a secret on a specific platform."""
    try:
        result = await secret_manager_service.create_secret(
            platform=request.platform,
            scope=request.scope,
            key=request.key,
            value=request.value,
            protected=request.protected,
            masked=request.masked,
            environment_scope=request.environment_scope,
            description=request.description,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Create failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update")
async def update_secret(request: UpdateSecretRequest):
    """Update a secret on a specific platform."""
    try:
        result = await secret_manager_service.update_secret(
            platform=request.platform,
            scope=request.scope,
            key=request.key,
            value=request.value,
            protected=request.protected,
            masked=request.masked,
            environment_scope=request.environment_scope,
            description=request.description,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Update failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
async def delete_secret(request: DeleteSecretRequest):
    """Delete a secret from a specific platform."""
    try:
        result = await secret_manager_service.delete_secret(
            platform=request.platform,
            scope=request.scope,
            key=request.key,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
