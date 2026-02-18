"""
File: github.py
Purpose: GitHub/Gitea REST API client for managing repositories, branches, file contents, workflows,
         and Actions runs. Supports both GitHub.com and self-hosted Gitea servers using the compatible
         API surface (repos, contents, branches, actions/runs, actions/secrets).
When Used: Called by the GitHub pipeline committer to push workflow files to Gitea, by the status
           module to monitor Gitea Actions runs, and by the secret_manager to manage org-level
           secrets. Uses 'token' auth format required by Gitea for write operations.
Why Created: Provides a unified client for GitHub-compatible APIs so the GitHub Actions pipeline
             generator can work with Gitea (the dev-stack's source control) using the same
             interface that would work against real GitHub.com or GitHub Enterprise.
"""
from typing import List, Optional, Dict, Any
import base64
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class GitHubIntegration(BaseIntegration):
    """GitHub API integration for repository and workflow operations"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)
        self._token = config.token

    @property
    def name(self) -> str:
        return "github"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def health_check(self) -> ToolStatus:
        """Check if GitHub API is accessible"""
        try:
            response = await self.get("/api/v3/zen" if "/api/v3" not in self.config.base_url else "/zen")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            # Try alternate endpoint for GitHub Enterprise / Gitea
            response = await self.get("/api/v1/version")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        """Get GitHub/Gitea version"""
        try:
            # Try Gitea version endpoint
            response = await self.get("/api/v1/version")
            if response.status_code == 200:
                data = response.json()
                return data.get("version", "unknown")
            # GitHub doesn't have a version endpoint, return API version
            return "GitHub API v3"
        except Exception:
            return None

    # ========================================================================
    # User & Authentication
    # ========================================================================

    async def get_authenticated_user(self) -> Dict[str, Any]:
        """Get the authenticated user"""
        response = await self.get("/user")
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Repositories
    # ========================================================================

    async def list_repositories(
        self,
        org: Optional[str] = None,
        visibility: Optional[str] = None,
        per_page: int = 30,
        page: int = 1
    ) -> List[Dict[str, Any]]:
        """List repositories"""
        params = {"per_page": per_page, "page": page}
        if visibility:
            params["visibility"] = visibility

        if org:
            endpoint = f"/orgs/{org}/repos"
        else:
            endpoint = "/user/repos"

        response = await self.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()

    async def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get a specific repository"""
        response = await self.get(f"/repos/{owner}/{repo}")
        response.raise_for_status()
        return response.json()

    async def create_repository(
        self,
        name: str,
        description: Optional[str] = None,
        private: bool = True,
        auto_init: bool = True,
        org: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new repository"""
        payload = {
            "name": name,
            "private": private,
            "auto_init": auto_init
        }
        if description:
            payload["description"] = description

        if org:
            endpoint = f"/orgs/{org}/repos"
        else:
            endpoint = "/user/repos"

        response = await self.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()

    async def get_repository_tree(
        self,
        owner: str,
        repo: str,
        ref: str = "main",
        recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """Get repository file tree"""
        params = {"recursive": "1" if recursive else "0"}
        response = await self.get(f"/repos/{owner}/{repo}/git/trees/{ref}", params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("tree", [])

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = "main"
    ) -> str:
        """Get file content from repository"""
        params = {"ref": ref}
        response = await self.get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
        response.raise_for_status()
        data = response.json()

        if data.get("encoding") == "base64":
            content = base64.b64decode(data["content"]).decode("utf-8")
        else:
            content = data.get("content", "")

        return content

    async def list_files(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str = "main"
    ) -> List[Dict[str, Any]]:
        """List files in a directory"""
        params = {"ref": ref}
        response = await self.get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Branches
    # ========================================================================

    async def list_branches(self, owner: str, repo: str, per_page: int = 30) -> List[Dict[str, Any]]:
        """List branches in a repository"""
        params = {"per_page": per_page}
        response = await self.get(f"/repos/{owner}/{repo}/branches", params=params)
        response.raise_for_status()
        return response.json()

    async def get_branch(self, owner: str, repo: str, branch: str) -> Dict[str, Any]:
        """Get a specific branch"""
        response = await self.get(f"/repos/{owner}/{repo}/branches/{branch}")
        response.raise_for_status()
        return response.json()

    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
        from_ref: str = "main"
    ) -> Dict[str, Any]:
        """Create a new branch"""
        # Get the SHA of the source branch
        source_branch = await self.get_branch(owner, repo, from_ref)
        sha = source_branch["commit"]["sha"]

        payload = {
            "ref": f"refs/heads/{branch}",
            "sha": sha
        }
        response = await self.post(f"/repos/{owner}/{repo}/git/refs", json=payload)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Commits & Files
    # ========================================================================

    async def list_commits(
        self,
        owner: str,
        repo: str,
        ref: str = "main",
        per_page: int = 30
    ) -> List[Dict[str, Any]]:
        """List commits in a repository"""
        params = {"sha": ref, "per_page": per_page}
        response = await self.get(f"/repos/{owner}/{repo}/commits", params=params)
        response.raise_for_status()
        return response.json()

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
        sha: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create or update a file in the repository"""
        # Base64 encode the content
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "message": message,
            "content": encoded_content,
            "branch": branch
        }

        # If updating, we need the current file SHA
        if sha:
            payload["sha"] = sha
        else:
            # Try to get existing file SHA
            try:
                response = await self.get(f"/repos/{owner}/{repo}/contents/{path}", params={"ref": branch})
                if response.status_code == 200:
                    existing = response.json()
                    payload["sha"] = existing["sha"]
            except Exception:
                pass  # File doesn't exist, creating new

        response = await self.put(f"/repos/{owner}/{repo}/contents/{path}", json=payload)
        response.raise_for_status()
        return response.json()

    async def create_commit_with_files(
        self,
        owner: str,
        repo: str,
        files: Dict[str, str],
        message: str,
        branch: str = "main"
    ) -> Dict[str, Any]:
        """Create a commit with multiple files"""
        results = []
        for path, content in files.items():
            result = await self.create_or_update_file(
                owner, repo, path, content, message, branch
            )
            results.append(result)

        return {
            "success": True,
            "files_committed": len(results),
            "branch": branch,
            "commit_sha": results[-1]["commit"]["sha"] if results else None
        }

    # ========================================================================
    # Workflows (GitHub Actions)
    # ========================================================================

    async def list_workflows(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """List workflows in a repository"""
        response = await self.get(f"/repos/{owner}/{repo}/actions/workflows")
        response.raise_for_status()
        data = response.json()
        return data.get("workflows", [])

    async def get_workflow(self, owner: str, repo: str, workflow_id: int) -> Dict[str, Any]:
        """Get a specific workflow"""
        response = await self.get(f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}")
        response.raise_for_status()
        return response.json()

    async def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id: Optional[int] = None,
        branch: Optional[str] = None,
        status: Optional[str] = None,
        per_page: int = 30
    ) -> List[Dict[str, Any]]:
        """List workflow runs"""
        params = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status

        if workflow_id:
            endpoint = f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        else:
            endpoint = f"/repos/{owner}/{repo}/actions/runs"

        response = await self.get(endpoint, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("workflow_runs", [])

    async def get_workflow_run(self, owner: str, repo: str, run_id: int) -> Dict[str, Any]:
        """Get a specific workflow run"""
        response = await self.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    async def get_workflow_run_jobs(self, owner: str, repo: str, run_id: int) -> List[Dict[str, Any]]:
        """Get jobs for a workflow run"""
        response = await self.get(f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs")
        response.raise_for_status()
        data = response.json()
        return data.get("jobs", [])

    async def get_job_logs(self, owner: str, repo: str, job_id: int) -> str:
        """Get logs for a specific job"""
        # GitHub returns a redirect to the log file
        response = await self.get(f"/repos/{owner}/{repo}/actions/jobs/{job_id}/logs")
        if response.status_code == 302:
            # Follow the redirect
            log_url = response.headers.get("Location")
            if log_url:
                import httpx
                async with httpx.AsyncClient() as client:
                    log_response = await client.get(log_url)
                    return log_response.text
        return response.text

    async def rerun_workflow(self, owner: str, repo: str, run_id: int) -> Dict[str, Any]:
        """Re-run a workflow"""
        response = await self.post(f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun")
        response.raise_for_status()
        return {"success": True, "run_id": run_id}

    async def cancel_workflow_run(self, owner: str, repo: str, run_id: int) -> Dict[str, Any]:
        """Cancel a workflow run"""
        response = await self.post(f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel")
        response.raise_for_status()
        return {"success": True, "run_id": run_id}

    async def trigger_workflow(
        self,
        owner: str,
        repo: str,
        workflow_id: str,
        ref: str = "main",
        inputs: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Manually trigger a workflow dispatch event"""
        payload = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs

        response = await self.post(
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            json=payload
        )
        response.raise_for_status()
        return {"success": True, "workflow_id": workflow_id, "ref": ref}

    # ========================================================================
    # Runners (Self-hosted)
    # ========================================================================

    async def list_runners(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """List self-hosted runners for a repository"""
        response = await self.get(f"/repos/{owner}/{repo}/actions/runners")
        response.raise_for_status()
        data = response.json()
        return data.get("runners", [])

    async def list_org_runners(self, org: str) -> List[Dict[str, Any]]:
        """List self-hosted runners for an organization"""
        response = await self.get(f"/orgs/{org}/actions/runners")
        response.raise_for_status()
        data = response.json()
        return data.get("runners", [])

    async def get_runner_registration_token(self, owner: str, repo: str) -> str:
        """Get a registration token for self-hosted runners"""
        response = await self.post(f"/repos/{owner}/{repo}/actions/runners/registration-token")
        response.raise_for_status()
        data = response.json()
        return data.get("token")

    # ========================================================================
    # Pull Requests
    # ========================================================================

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 30
    ) -> List[Dict[str, Any]]:
        """List pull requests"""
        params = {"state": state, "per_page": per_page}
        response = await self.get(f"/repos/{owner}/{repo}/pulls", params=params)
        response.raise_for_status()
        return response.json()

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a pull request"""
        payload = {
            "title": title,
            "head": head,
            "base": base
        }
        if body:
            payload["body"] = body

        response = await self.post(f"/repos/{owner}/{repo}/pulls", json=payload)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Issues
    # ========================================================================

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create an issue"""
        payload = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels

        response = await self.post(f"/repos/{owner}/{repo}/issues", json=payload)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Secrets
    # ========================================================================

    async def list_secrets(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """List repository secrets (names only, not values)"""
        response = await self.get(f"/repos/{owner}/{repo}/actions/secrets")
        response.raise_for_status()
        data = response.json()
        return data.get("secrets", [])

    async def get_public_key(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get the public key for encrypting secrets"""
        response = await self.get(f"/repos/{owner}/{repo}/actions/secrets/public-key")
        response.raise_for_status()
        return response.json()
