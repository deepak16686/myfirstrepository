"""
File: rbac.py
Purpose: Provides REST endpoints for viewing the cross-tool access matrix, looking up per-user
    group memberships across all DevOps tools (GitLab, Jenkins, SonarQube, Nexus, etc.), and
    granting or revoking access to specific tool groups.
When Used: Invoked by the frontend RBAC / Access Manager tool card when an admin views the full
    access overview, inspects a user's permissions, or grants/revokes group membership via the
    /rbac/* routes.
Why Created: Centralizes role-based access control across all integrated DevOps tools into a
    single management interface, rather than requiring admins to log into each tool individually
    to manage user permissions.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import rbac_service

router = APIRouter(prefix="/rbac", tags=["RBAC - Access Manager"])


class AccessChangeRequest(BaseModel):
    username: str
    tool: str
    group: str


@router.get("/overview")
async def rbac_overview():
    """Get full access matrix: all users x all tools with group memberships."""
    try:
        return await rbac_service.get_overview()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{username}")
async def rbac_user_access(username: str):
    """Get a single user's access details across all tools."""
    result = await rbac_service.get_user_access(username)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "Not found"))
    return result


@router.post("/grant")
async def rbac_grant_access(req: AccessChangeRequest):
    """Grant a user access to a group in a specific tool."""
    result = await rbac_service.grant_access(req.username, req.tool, req.group)
    return result


@router.post("/revoke")
async def rbac_revoke_access(req: AccessChangeRequest):
    """Revoke a user's access from a group in a specific tool."""
    result = await rbac_service.revoke_access(req.username, req.tool, req.group)
    return result


@router.get("/tool-directory")
async def tool_directory():
    """Get all tools with browser URLs and credentials."""
    return rbac_service.get_tool_directory()
