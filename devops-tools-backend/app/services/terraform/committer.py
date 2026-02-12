"""
Git commit operations for Terraform configuration files.

Commits .tf files to Gitea repositories via Gitea API v1.
Uses the same Gitea instance as Jenkins pipelines.
"""
import base64
import httpx
from typing import Dict, Any, Optional
from datetime import datetime

from app.services.github_pipeline.analyzer import parse_github_url


async def commit_to_repo(
    repo_url: str,
    git_token: str,
    files: Dict[str, str],
    branch_name: Optional[str] = None,
    commit_message: str = "Add Terraform configuration [AI Generated]",
) -> Dict[str, Any]:
    """Commit Terraform .tf files to Gitea repository."""
    parsed = parse_github_url(repo_url)
    owner = parsed["owner"]
    repo = parsed["repo"]
    host = parsed["host"]

    if not branch_name:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"terraform-{timestamp}"

    api_base = f"{host}/api/v1/repos/{owner}/{repo}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"token {git_token}",
            "Accept": "application/json",
        }

        # Get default branch SHA
        base_sha = None
        default_branch = "main"
        for default in ["main", "master"]:
            branch_resp = await client.get(f"{api_base}/branches/{default}", headers=headers)
            if branch_resp.status_code == 200:
                base_sha = branch_resp.json()["commit"]["id"]
                default_branch = default
                break

        if not base_sha:
            return {"success": False, "error": "Could not find default branch"}

        # Create new branch
        create_ref_resp = await client.post(
            f"{api_base}/branches",
            headers=headers,
            json={"new_branch_name": branch_name, "old_branch_name": default_branch},
        )
        if create_ref_resp.status_code not in [200, 201]:
            # Branch might already exist
            pass

        # Commit each file
        last_commit = None
        for filepath, content in files.items():
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

            # Check if file exists on the new branch
            file_resp = await client.get(
                f"{api_base}/contents/{filepath}",
                headers=headers,
                params={"ref": branch_name},
            )

            payload = {
                "message": commit_message,
                "content": encoded,
                "branch": branch_name,
            }

            if file_resp.status_code == 200:
                payload["sha"] = file_resp.json()["sha"]
                resp = await client.put(
                    f"{api_base}/contents/{filepath}",
                    headers=headers,
                    json=payload,
                )
            else:
                resp = await client.post(
                    f"{api_base}/contents/{filepath}",
                    headers=headers,
                    json=payload,
                )

            if resp.status_code in [200, 201]:
                last_commit = resp.json()

        if last_commit:
            browser_host = host.replace("gitea-server:3000", "localhost:3002")
            return {
                "success": True,
                "branch": branch_name,
                "commit_id": last_commit.get("commit", {}).get("sha", ""),
                "web_url": f"{browser_host}/{owner}/{repo}/src/branch/{branch_name}",
                "project_id": 0,
            }

    return {"success": False, "error": "Failed to commit files"}
