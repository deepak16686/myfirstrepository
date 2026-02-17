"""
Release Notes Generator Router

Endpoints for generating release notes from git commits via LLM.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.release_notes import release_notes_service
from app.services.commit_history import commit_history_service

router = APIRouter(prefix="/release-notes", tags=["Release Notes"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    repo_url: str
    token: Optional[str] = None
    since: str
    until: str
    branch: Optional[str] = None
    format_style: str = "standard"


class BranchQuery(BaseModel):
    repo_url: str
    token: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_release_notes(request: GenerateRequest):
    """Generate release notes from commits in the specified range."""
    try:
        result = await release_notes_service.generate_release_notes(
            repo_url=request.repo_url,
            token=request.token,
            since=request.since,
            until=request.until,
            branch=request.branch,
            format_style=request.format_style,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Generation failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/branches")
async def list_branches(query: BranchQuery):
    """List branches for a repository (proxy to commit history service)."""
    try:
        result = await commit_history_service.get_branches(
            repo_url=query.repo_url,
            token=query.token,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
