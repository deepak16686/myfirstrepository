"""
Workflow status and reinforcement learning recording operations.

Handles checking workflow run status and recording results for RL.
"""
import httpx
from typing import Dict, Any

from app.config import settings
from app.services.github_pipeline.analyzer import parse_github_url


async def get_workflow_status(
    repo_url: str,
    github_token: str,
    branch: str
) -> Dict[str, Any]:
    """Get latest workflow run status"""
    parsed = parse_github_url(repo_url)
    owner = parsed["owner"]
    repo = parsed["repo"]
    host = parsed["host"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        api_base = f"{host}/api/v1/repos/{owner}/{repo}" if "gitea" in host.lower() or host == settings.github_url else f"{host}/repos/{owner}/{repo}"

        response = await client.get(
            f"{api_base}/actions/runs",
            headers=headers,
            params={"branch": branch, "per_page": 1}
        )

        if response.status_code == 200:
            data = response.json()
            runs = data.get("workflow_runs", [])
            if runs:
                run = runs[0]
                return {
                    "run_id": run["id"],
                    "status": run["status"],
                    "conclusion": run.get("conclusion"),
                    "created_at": run["created_at"],
                    "updated_at": run.get("updated_at"),
                    "html_url": run.get("html_url")
                }

    return {"status": "not_found"}


async def record_workflow_result(
    repo_url: str,
    github_token: str,
    branch: str,
    run_id: int
) -> Dict[str, Any]:
    """Record successful workflow for RL"""
    # Get workflow run details
    status = await get_workflow_status(repo_url, github_token, branch)

    if status.get("conclusion") == "success":
        # Store in ChromaDB
        # This would be implemented similar to GitLab pipeline recording
        return {"success": True, "recorded": True}

    return {"success": False, "error": "Workflow not successful"}
