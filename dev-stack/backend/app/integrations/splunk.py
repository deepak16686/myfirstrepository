"""
File: splunk.py
Purpose: Splunk HTTP Event Collector (HEC) client for sending pipeline events and performing health
         checks. Handles self-signed TLS certificates (verify=False) common in development Splunk
         instances and uses the 'Splunk <token>' authorization header format.
When Used: Called by the connectivity router for health checks. Pipeline notify stages send events
           directly via curl/wget in the generated CI/CD YAML using the HEC token from Vault.
Why Created: Provides observability into pipeline execution by forwarding build events to Splunk,
             enabling dashboards that track pipeline success rates and failure patterns.
"""
import httpx
from typing import Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class SplunkIntegration(BaseIntegration):
    """Splunk HEC integration for health checks and event forwarding"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)
        # Splunk HEC uses HTTPS with self-signed certs
        self.client = httpx.AsyncClient(timeout=30.0, verify=False)

    @property
    def name(self) -> str:
        return "splunk"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Splunk {self.config.token}"
        return headers

    def _get_auth(self) -> Optional[tuple]:
        return None

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/services/collector/health/1.0")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/services/collector/health/1.0")
            if response.status_code == 200:
                data = response.json()
                return data.get("version", "HEC Active")
        except Exception:
            pass
        return None

    async def send_event(self, event: Dict[str, Any]) -> bool:
        """Send an event to Splunk HEC"""
        response = await self.post("/services/collector/event", json={"event": event})
        return response.status_code == 200
