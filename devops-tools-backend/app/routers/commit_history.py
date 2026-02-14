"""
Commit History Router

Endpoints for fetching commit history from GitLab and Gitea repositories.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.services.commit_history import commit_history_service

router = APIRouter(prefix="/commit-history", tags=["Commit History"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BranchQuery(BaseModel):
    repo_url: str
    token: Optional[str] = None


class CommitQuery(BaseModel):
    repo_url: str
    token: Optional[str] = None
    since: str  # ISO datetime e.g. "2026-02-10T00:00:00"
    until: str  # ISO datetime e.g. "2026-02-14T23:59:59"
    branch: Optional[str] = None  # Branch name to filter commits
    page: int = 1
    per_page: int = 50


class CommitDetailQuery(BaseModel):
    repo_url: str
    token: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/branches")
async def list_branches(query: BranchQuery):
    """List all branches for a repository."""
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


@router.post("/commits")
async def list_commits(query: CommitQuery):
    """Fetch commits from a repository within a date range."""
    try:
        result = await commit_history_service.get_commits(
            repo_url=query.repo_url,
            token=query.token,
            since=query.since,
            until=query.until,
            branch=query.branch,
            page=query.page,
            per_page=query.per_page,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commits/{sha}/detail")
async def commit_detail(sha: str, query: CommitDetailQuery):
    """Fetch a single commit with changed files."""
    try:
        result = await commit_history_service.get_commit_detail(
            repo_url=query.repo_url,
            token=query.token,
            commit_sha=sha,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
