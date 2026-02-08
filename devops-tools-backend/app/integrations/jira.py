"""
Jira Software API Integration
"""
from typing import List, Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class JiraIntegration(BaseIntegration):
    """Jira REST API v2 integration"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "jira"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def _get_auth(self) -> Optional[tuple]:
        if self.config.username and self.config.api_key:
            return (self.config.username, self.config.api_key)
        if self.config.username and self.config.password:
            return (self.config.username, self.config.password)
        return None

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/rest/api/2/serverInfo")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            # Fallback: /status works even during setup wizard
            response = await self.get("/status")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/rest/api/2/serverInfo")
            if response.status_code == 200:
                data = response.json()
                return data.get("version")
            # Fallback: report state from /status
            response = await self.get("/status")
            if response.status_code == 200:
                data = response.json()
                state = data.get("state", "unknown")
                return f"Setup: {state}"
        except Exception:
            pass
        return None

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a Jira issue"""
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type}
            }
        }
        if labels:
            payload["fields"]["labels"] = labels

        response = await self.post("/rest/api/2/issue", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_issue(self, issue_key: str) -> Optional[Dict[str, Any]]:
        """Get a Jira issue by key"""
        response = await self.get(f"/rest/api/2/issue/{issue_key}")
        if response.status_code == 200:
            return response.json()
        return None

    async def list_projects(self) -> List[Dict[str, Any]]:
        """List all Jira projects"""
        response = await self.get("/rest/api/2/project")
        response.raise_for_status()
        return response.json()
