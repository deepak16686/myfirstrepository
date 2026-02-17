"""
GitLab Commit Functions

Standalone async function for committing files to GitLab repositories.
"""
from typing import Dict, Any

import httpx

from .analyzer import parse_gitlab_url


async def commit_to_gitlab(
    repo_url: str,
    gitlab_token: str,
    files: Dict[str, str],
    branch_name: str,
    commit_message: str = "Add CI/CD pipeline configuration"
) -> Dict[str, Any]:
    """
    Commit generated files to a new branch in GitLab.

    Args:
        repo_url: GitLab repository URL
        gitlab_token: GitLab access token
        files: Dict of filename -> content
        branch_name: Name for the new branch
        commit_message: Commit message
    """
    parsed = parse_gitlab_url(repo_url)

    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {
            "PRIVATE-TOKEN": gitlab_token,
            "Content-Type": "application/json"
        }

        # Get default branch
        project_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}"
        project_resp = await client.get(project_url, headers=headers)
        project_resp.raise_for_status()
        project = project_resp.json()
        default_branch = project.get('default_branch', 'main')

        # Check if target branch already exists
        branch_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/branches/{branch_name.replace('/', '%2F')}"
        branch_resp = await client.get(branch_url, headers=headers)
        branch_exists = branch_resp.status_code == 200

        # Check file existence on the correct ref
        check_ref = branch_name if branch_exists else default_branch

        # Create commit with new branch
        actions = []
        for filename, content in files.items():
            # Check if file exists on the correct branch
            file_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/files/{filename.replace('/', '%2F')}"
            file_resp = await client.get(
                file_url,
                headers=headers,
                params={"ref": check_ref}
            )

            action = "update" if file_resp.status_code == 200 else "create"
            actions.append({
                "action": action,
                "file_path": filename,
                "content": content
            })

        # Create commit
        commit_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/commits"
        commit_data = {
            "branch": branch_name,
            "commit_message": commit_message,
            "actions": actions
        }
        # Only set start_branch when creating a new branch
        if not branch_exists:
            commit_data["start_branch"] = default_branch

        commit_resp = await client.post(commit_url, headers=headers, json=commit_data)
        commit_resp.raise_for_status()
        commit = commit_resp.json()

        return {
            "success": True,
            "commit_id": commit.get('id'),
            "branch": branch_name,
            "web_url": commit.get('web_url'),
            "project_id": project['id']
        }
