"""
File: release_notes.py
Purpose: Provides REST endpoints for generating LLM-summarized release notes from git commits
    within a date range, and for listing repository branches as a convenience proxy to the
    commit history service.
When Used: Invoked by the frontend Release Notes Generator tool card when a user selects a
    repository, date range, and format style to auto-generate release notes via the
    /release-notes/* routes.
Why Created: Combines the commit history service (raw commit fetching) with LLM summarization
    into a purpose-built release notes workflow, keeping this higher-level orchestration
    separate from the raw commit history endpoints.
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
