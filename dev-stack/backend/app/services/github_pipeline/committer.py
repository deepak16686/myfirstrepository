"""
Git commit operations for GitHub/Gitea repositories.

Handles committing workflow and Dockerfile to repositories via API.
"""
import base64
import httpx
from typing import Dict, Any, Optional
from datetime import datetime

from app.config import settings
from app.services.github_pipeline.analyzer import parse_github_url


async def commit_to_github(
    repo_url: str,
    github_token: str,
    workflow: str,
    dockerfile: str,
    branch_name: Optional[str] = None,
    commit_message: str = "Add CI/CD pipeline configuration [AI Generated]"
) -> Dict[str, Any]:
    """Commit workflow and Dockerfile to GitHub/Gitea repository"""
    parsed = parse_github_url(repo_url)
    owner = parsed["owner"]
    repo = parsed["repo"]
    host = parsed["host"]

    # Generate branch name if not provided
    if not branch_name:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"ci-pipeline-{timestamp}"

    api_base = f"{host}/api/v1/repos/{owner}/{repo}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/json",
        }

        # Get default branch SHA
        default_branch = "main"
        branch_response = await client.get(
            f"{api_base}/branches/main",
            headers=headers
        )
        if branch_response.status_code != 200:
            default_branch = "master"
            branch_response = await client.get(
                f"{api_base}/branches/master",
                headers=headers
            )

        if branch_response.status_code == 200:
            branch_data = branch_response.json()
            # Gitea uses commit.id, GitHub uses commit.sha
            base_sha = branch_data["commit"].get("id") or branch_data["commit"].get("sha")
        else:
            return {"success": False, "error": "Could not find default branch"}

        # Create new branch (Gitea API)
        create_branch_response = await client.post(
            f"{api_base}/branches",
            headers=headers,
            json={
                "new_branch_name": branch_name,
                "old_branch_name": default_branch
            }
        )

        if create_branch_response.status_code not in [200, 201]:
            # Branch might already exist, continue anyway
            pass

        # Commit files
        files_to_commit = {
            ".github/workflows/ci.yml": workflow,
            "Dockerfile": dockerfile
        }

        last_commit = None
        for path, content in files_to_commit.items():
            encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

            # Check if file exists on the branch
            file_response = await client.get(
                f"{api_base}/contents/{path}",
                headers=headers,
                params={"ref": branch_name}
            )

            payload = {
                "message": commit_message,
                "content": encoded_content,
                "branch": branch_name,
            }

            if file_response.status_code == 200:
                # File exists — use PUT with SHA to update
                payload["sha"] = file_response.json()["sha"]
                resp = await client.put(
                    f"{api_base}/contents/{path}",
                    headers=headers,
                    json=payload,
                )
            else:
                # File doesn't exist — use POST to create
                resp = await client.post(
                    f"{api_base}/contents/{path}",
                    headers=headers,
                    json=payload,
                )

            if resp.status_code in [200, 201]:
                last_commit = resp.json()

        if last_commit:
            # Use browser-accessible URL for the web link
            browser_host = host.replace("gitea-server:3000", "localhost:3002")
            return {
                "success": True,
                "branch": branch_name,
                "commit_sha": last_commit.get("commit", {}).get("sha", ""),
                "web_url": f"{browser_host}/{owner}/{repo}/src/branch/{branch_name}",
            }

    return {"success": False, "error": "Failed to commit files"}
