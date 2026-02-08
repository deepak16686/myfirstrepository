"""
Git commit operations for GitHub/Gitea repositories.

Handles committing workflow and Dockerfile to repositories via API.
"""
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

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        # Determine API base path
        api_base = f"{host}/api/v1/repos/{owner}/{repo}" if "gitea" in host.lower() or host == settings.github_url else f"{host}/repos/{owner}/{repo}"

        # Get default branch SHA
        branch_response = await client.get(
            f"{api_base}/branches/main",
            headers=headers
        )
        if branch_response.status_code != 200:
            # Try 'master' as fallback
            branch_response = await client.get(
                f"{api_base}/branches/master",
                headers=headers
            )

        if branch_response.status_code == 200:
            branch_data = branch_response.json()
            base_sha = branch_data["commit"]["sha"]
        else:
            return {"success": False, "error": "Could not find default branch"}

        # Create new branch
        create_ref_response = await client.post(
            f"{api_base}/git/refs",
            headers=headers,
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha
            }
        )

        if create_ref_response.status_code not in [200, 201]:
            # Branch might already exist, continue anyway
            pass

        # Commit files
        files_to_commit = {
            ".github/workflows/ci.yml": workflow,
            "Dockerfile": dockerfile
        }

        last_commit = None
        for path, content in files_to_commit.items():
            encoded_content = __import__('base64').b64encode(content.encode('utf-8')).decode('utf-8')

            # Check if file exists
            file_response = await client.get(
                f"{api_base}/contents/{path}",
                headers=headers,
                params={"ref": branch_name}
            )

            payload = {
                "message": commit_message,
                "content": encoded_content,
                "branch": branch_name
            }

            if file_response.status_code == 200:
                existing = file_response.json()
                payload["sha"] = existing["sha"]

            commit_response = await client.put(
                f"{api_base}/contents/{path}",
                headers=headers,
                json=payload
            )

            if commit_response.status_code in [200, 201]:
                last_commit = commit_response.json()

        if last_commit:
            return {
                "success": True,
                "branch": branch_name,
                "commit_sha": last_commit.get("commit", {}).get("sha"),
                "web_url": f"{host}/{owner}/{repo}/tree/{branch_name}"
            }

    return {"success": False, "error": "Failed to commit files"}
