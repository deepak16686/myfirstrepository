"""
SonarQube API Integration
"""
from typing import List, Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import (
    ToolStatus, SonarQubeProject, SonarQubeMetric,
    SonarQubeQualityGate, SonarQubeIssue
)


class SonarQubeIntegration(BaseIntegration):
    """SonarQube API integration"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "sonarqube"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # SonarQube can use token as username with empty password
        return headers

    def _get_auth(self) -> Optional[tuple]:
        if self.config.token:
            # Token-based auth: token as username, empty password
            return (self.config.token, "")
        elif self.config.username and self.config.password:
            return (self.config.username, self.config.password)
        return None

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/api/system/status")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "UP":
                    return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/api/system/status")
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
        page_size: int = 50,
        page: int = 1
    ) -> List[SonarQubeProject]:
        """List SonarQube projects"""
        params = {"ps": page_size, "p": page}
        if search:
            params["q"] = search

        response = await self.get("/api/projects/search", params=params)
        response.raise_for_status()
        data = response.json()
        return [SonarQubeProject(**p) for p in data.get("components", [])]

    async def get_project(self, project_key: str) -> Optional[SonarQubeProject]:
        """Get a specific project by key"""
        params = {"component": project_key}
        response = await self.get("/api/components/show", params=params)
        if response.status_code == 200:
            data = response.json()
            return SonarQubeProject(**data.get("component", {}))
        return None

    async def create_project(
        self,
        project_key: str,
        name: str,
        visibility: str = "private"
    ) -> SonarQubeProject:
        """Create a new project"""
        params = {
            "project": project_key,
            "name": name,
            "visibility": visibility
        }
        response = await self.post("/api/projects/create", params=params)
        response.raise_for_status()
        data = response.json()
        return SonarQubeProject(**data.get("project", {}))

    async def delete_project(self, project_key: str) -> bool:
        """Delete a project"""
        params = {"project": project_key}
        response = await self.post("/api/projects/delete", params=params)
        return response.status_code == 204

    # ========================================================================
    # Quality Gates
    # ========================================================================

    async def get_quality_gate_status(self, project_key: str) -> SonarQubeQualityGate:
        """Get quality gate status for a project"""
        params = {"projectKey": project_key}
        response = await self.get("/api/qualitygates/project_status", params=params)
        response.raise_for_status()
        data = response.json()
        project_status = data.get("projectStatus", {})
        return SonarQubeQualityGate(
            project_key=project_key,
            status=project_status.get("status", "UNKNOWN"),
            conditions=project_status.get("conditions", [])
        )

    async def list_quality_gates(self) -> List[Dict[str, Any]]:
        """List all quality gates"""
        response = await self.get("/api/qualitygates/list")
        response.raise_for_status()
        data = response.json()
        return data.get("qualitygates", [])

    # ========================================================================
    # Metrics & Measures
    # ========================================================================

    async def get_metrics(
        self,
        project_key: str,
        metrics: List[str] = None
    ) -> List[SonarQubeMetric]:
        """Get metrics for a project"""
        if metrics is None:
            metrics = [
                "bugs", "vulnerabilities", "code_smells", "coverage",
                "duplicated_lines_density", "ncloc", "sqale_index",
                "reliability_rating", "security_rating", "sqale_rating"
            ]

        params = {
            "component": project_key,
            "metricKeys": ",".join(metrics)
        }
        response = await self.get("/api/measures/component", params=params)
        response.raise_for_status()
        data = response.json()

        result = []
        for measure in data.get("component", {}).get("measures", []):
            result.append(SonarQubeMetric(
                metric=measure.get("metric"),
                value=measure.get("value", ""),
                component=project_key
            ))
        return result

    # ========================================================================
    # Issues
    # ========================================================================

    async def list_issues(
        self,
        project_key: str,
        severities: Optional[str] = None,
        types: Optional[str] = None,
        statuses: str = "OPEN,CONFIRMED,REOPENED",
        page_size: int = 100,
        page: int = 1
    ) -> List[SonarQubeIssue]:
        """List issues for a project"""
        params = {
            "componentKeys": project_key,
            "statuses": statuses,
            "ps": page_size,
            "p": page
        }
        if severities:
            params["severities"] = severities
        if types:
            params["types"] = types

        response = await self.get("/api/issues/search", params=params)
        response.raise_for_status()
        data = response.json()

        return [
            SonarQubeIssue(
                key=issue.get("key"),
                rule=issue.get("rule"),
                severity=issue.get("severity"),
                component=issue.get("component"),
                message=issue.get("message"),
                line=issue.get("line"),
                status=issue.get("status"),
                type=issue.get("type")
            )
            for issue in data.get("issues", [])
        ]

    async def get_issue_count(self, project_key: str) -> Dict[str, int]:
        """Get issue counts by severity"""
        params = {
            "componentKeys": project_key,
            "facets": "severities,types",
            "ps": 1
        }
        response = await self.get("/api/issues/search", params=params)
        response.raise_for_status()
        data = response.json()

        counts = {"total": data.get("total", 0)}
        for facet in data.get("facets", []):
            if facet.get("property") == "severities":
                for value in facet.get("values", []):
                    counts[value.get("val", "").lower()] = value.get("count", 0)
        return counts

    # ========================================================================
    # Analysis
    # ========================================================================

    async def get_analysis_history(
        self,
        project_key: str,
        page_size: int = 10
    ) -> List[Dict[str, Any]]:
        """Get analysis history for a project"""
        params = {
            "project": project_key,
            "ps": page_size
        }
        response = await self.get("/api/project_analyses/search", params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("analyses", [])

    # ========================================================================
    # Tokens
    # ========================================================================

    async def generate_token(self, name: str, project_key: Optional[str] = None) -> Dict[str, Any]:
        """Generate a new user token"""
        params = {"name": name}
        if project_key:
            params["projectKey"] = project_key
            params["type"] = "PROJECT_ANALYSIS_TOKEN"
        else:
            params["type"] = "USER_TOKEN"

        response = await self.post("/api/user_tokens/generate", params=params)
        response.raise_for_status()
        return response.json()
