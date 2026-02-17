"""
GitLab API Integration
"""
from typing import List, Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import (
    ToolStatus, GitLabProject, GitLabPipeline, GitLabJob
)


class GitLabIntegration(BaseIntegration):
    """GitLab API integration"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)
        # GitLab uses Private-Token header
        self._token = config.token

    @property
    def name(self) -> str:
        return "gitlab"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["PRIVATE-TOKEN"] = self._token
        return headers

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/api/v4/version")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/api/v4/version")
            if response.status_code == 200:
                data = response.json()
                return data.get("version")
        except Exception:
            pass
        return None

    # ========================================================================
    # Projects
    # ========================================================================

    async def list_projects(
        self,
        search: Optional[str] = None,
        visibility: Optional[str] = None,
        per_page: int = 20,
        page: int = 1
    ) -> List[GitLabProject]:
        """List GitLab projects"""
        params = {"per_page": per_page, "page": page}
        if search:
            params["search"] = search
        if visibility:
            params["visibility"] = visibility

        response = await self.get("/api/v4/projects", params=params)
        response.raise_for_status()
        return [GitLabProject(**p) for p in response.json()]

    async def get_project(self, project_id: int) -> GitLabProject:
        """Get a specific project"""
        response = await self.get(f"/api/v4/projects/{project_id}")
        response.raise_for_status()
        return GitLabProject(**response.json())

    async def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        visibility: str = "private",
        initialize_with_readme: bool = True
    ) -> GitLabProject:
        """Create a new project"""
        payload = {
            "name": name,
            "visibility": visibility,
            "initialize_with_readme": initialize_with_readme
        }
        if description:
            payload["description"] = description

        response = await self.post("/api/v4/projects", json=payload)
        response.raise_for_status()
        return GitLabProject(**response.json())

    # ========================================================================
    # Pipelines
    # ========================================================================

    async def list_pipelines(
        self,
        project_id: int,
        status: Optional[str] = None,
        ref: Optional[str] = None,
        per_page: int = 20
    ) -> List[GitLabPipeline]:
        """List pipelines for a project"""
        params = {"per_page": per_page}
        if status:
            params["status"] = status
        if ref:
            params["ref"] = ref

        response = await self.get(f"/api/v4/projects/{project_id}/pipelines", params=params)
        response.raise_for_status()
        return [GitLabPipeline(**p) for p in response.json()]

    async def get_pipeline(self, project_id: int, pipeline_id: int) -> GitLabPipeline:
        """Get a specific pipeline"""
        response = await self.get(f"/api/v4/projects/{project_id}/pipelines/{pipeline_id}")
        response.raise_for_status()
        return GitLabPipeline(**response.json())

    async def trigger_pipeline(
        self,
        project_id: int,
        ref: str = "main",
        variables: Optional[Dict[str, str]] = None
    ) -> GitLabPipeline:
        """Trigger a new pipeline"""
        payload = {"ref": ref}
        if variables:
            payload["variables"] = [{"key": k, "value": v} for k, v in variables.items()]

        response = await self.post(f"/api/v4/projects/{project_id}/pipeline", json=payload)
        response.raise_for_status()
        return GitLabPipeline(**response.json())

    async def cancel_pipeline(self, project_id: int, pipeline_id: int) -> GitLabPipeline:
        """Cancel a running pipeline"""
        response = await self.post(f"/api/v4/projects/{project_id}/pipelines/{pipeline_id}/cancel")
        response.raise_for_status()
        return GitLabPipeline(**response.json())

    async def retry_pipeline(self, project_id: int, pipeline_id: int) -> GitLabPipeline:
        """Retry a failed pipeline"""
        response = await self.post(f"/api/v4/projects/{project_id}/pipelines/{pipeline_id}/retry")
        response.raise_for_status()
        return GitLabPipeline(**response.json())

    # ========================================================================
    # Jobs
    # ========================================================================

    async def list_pipeline_jobs(
        self,
        project_id: int,
        pipeline_id: int
    ) -> List[GitLabJob]:
        """List jobs in a pipeline"""
        response = await self.get(f"/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs")
        response.raise_for_status()
        return [GitLabJob(**j) for j in response.json()]

    async def get_job_log(self, project_id: int, job_id: int) -> str:
        """Get job log output"""
        response = await self.get(f"/api/v4/projects/{project_id}/jobs/{job_id}/trace")
        response.raise_for_status()
        return response.text

    async def retry_job(self, project_id: int, job_id: int) -> GitLabJob:
        """Retry a failed job"""
        response = await self.post(f"/api/v4/projects/{project_id}/jobs/{job_id}/retry")
        response.raise_for_status()
        return GitLabJob(**response.json())

    # ========================================================================
    # Branches & Commits
    # ========================================================================

    async def list_branches(self, project_id: int) -> List[Dict[str, Any]]:
        """List branches in a project"""
        response = await self.get(f"/api/v4/projects/{project_id}/repository/branches")
        response.raise_for_status()
        return response.json()

    async def list_commits(
        self,
        project_id: int,
        ref: str = "main",
        per_page: int = 20
    ) -> List[Dict[str, Any]]:
        """List commits in a project"""
        params = {"ref_name": ref, "per_page": per_page}
        response = await self.get(f"/api/v4/projects/{project_id}/repository/commits", params=params)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Merge Requests
    # ========================================================================

    async def list_merge_requests(
        self,
        project_id: int,
        state: str = "opened",
        per_page: int = 20
    ) -> List[Dict[str, Any]]:
        """List merge requests"""
        params = {"state": state, "per_page": per_page}
        response = await self.get(f"/api/v4/projects/{project_id}/merge_requests", params=params)
        response.raise_for_status()
        return response.json()

    async def create_merge_request(
        self,
        project_id: int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a merge request"""
        payload = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title
        }
        if description:
            payload["description"] = description

        response = await self.post(f"/api/v4/projects/{project_id}/merge_requests", json=payload)
        response.raise_for_status()
        return response.json()
