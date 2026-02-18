"""
File: jenkins.py
Purpose: Jenkins REST API client for managing jobs, builds, and nodes. Handles the /jenkins context
         path prefix and Basic auth required by Jenkins' security model.
When Used: Called by the Jenkins pipeline status module (to check build results and trigger scans),
           by the connectivity router (for health checks), and available through the unified dispatch.
Why Created: Wraps Jenkins' REST API into the BaseIntegration pattern so the Jenkins pipeline generator
             can trigger builds, check status, and fetch console output programmatically.
"""
from typing import Optional, Dict, Any, List
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class JenkinsIntegration(BaseIntegration):
    """Jenkins REST API integration"""

    # Jenkins may have a context path (e.g. /jenkins/)
    CONTEXT_PATH = "/jenkins"

    def __init__(self, config: ToolConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "jenkins"

    async def health_check(self) -> ToolStatus:
        try:
            # Try with context path first, then without
            for prefix in [self.CONTEXT_PATH, ""]:
                response = await self.get(f"{prefix}/api/json")
                if response.headers.get("X-Jenkins"):
                    return ToolStatus.HEALTHY
                if response.status_code == 200:
                    return ToolStatus.HEALTHY
                # 403 with X-Jenkins header means Jenkins is running but requires auth
                if response.status_code == 403 and response.headers.get("X-Jenkins"):
                    return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            for prefix in [self.CONTEXT_PATH, ""]:
                response = await self.get(f"{prefix}/api/json")
                version = response.headers.get("X-Jenkins")
                if version:
                    return version
        except Exception:
            pass
        return None

    async def list_jobs(self) -> List[Dict[str, Any]]:
        """List all Jenkins jobs"""
        response = await self.get(f"{self.CONTEXT_PATH}/api/json?tree=jobs[name,url,color]")
        response.raise_for_status()
        return response.json().get("jobs", [])

    async def get_job(self, job_name: str) -> Optional[Dict[str, Any]]:
        """Get details of a specific job"""
        response = await self.get(f"{self.CONTEXT_PATH}/job/{job_name}/api/json")
        if response.status_code == 200:
            return response.json()
        return None
