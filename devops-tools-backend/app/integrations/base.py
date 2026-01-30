"""
Base class for tool integrations
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import httpx
import time
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class BaseIntegration(ABC):
    """Base class for all tool integrations"""

    def __init__(self, config: ToolConfig):
        self.config = config
        self.client = httpx.AsyncClient(timeout=30.0)

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name"""
        pass

    @abstractmethod
    async def health_check(self) -> ToolStatus:
        """Check if the tool is healthy"""
        pass

    @abstractmethod
    async def get_version(self) -> Optional[str]:
        """Get tool version"""
        pass

    def _get_headers(self) -> Dict[str, str]:
        """Get default headers for API requests"""
        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        elif self.config.api_key:
            headers["X-API-Key"] = self.config.api_key
        return headers

    def _get_auth(self) -> Optional[tuple]:
        """Get basic auth credentials if configured"""
        if self.config.username and self.config.password:
            return (self.config.username, self.config.password)
        return None

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict] = None
    ) -> httpx.Response:
        """Make an HTTP request to the tool API"""
        url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        req_headers = self._get_headers()
        if headers:
            req_headers.update(headers)

        response = await self.client.request(
            method=method,
            url=url,
            params=params,
            json=json,
            data=data,
            headers=req_headers,
            auth=self._get_auth()
        )
        return response

    async def get(self, endpoint: str, params: Optional[Dict] = None, **kwargs) -> httpx.Response:
        return await self._request("GET", endpoint, params=params, **kwargs)

    async def post(self, endpoint: str, json: Optional[Dict] = None, **kwargs) -> httpx.Response:
        return await self._request("POST", endpoint, json=json, **kwargs)

    async def put(self, endpoint: str, json: Optional[Dict] = None, **kwargs) -> httpx.Response:
        return await self._request("PUT", endpoint, json=json, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> httpx.Response:
        return await self._request("DELETE", endpoint, **kwargs)

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class ToolExecutor:
    """Executes tool actions and tracks execution time"""

    @staticmethod
    async def execute(integration: BaseIntegration, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool action and return results with timing"""
        start_time = time.time()
        try:
            # Get the method from the integration
            method = getattr(integration, action, None)
            if method is None:
                return {
                    "success": False,
                    "result": None,
                    "error": f"Action '{action}' not found on {integration.name}",
                    "execution_time": time.time() - start_time
                }

            result = await method(**params)
            return {
                "success": True,
                "result": result,
                "error": None,
                "execution_time": time.time() - start_time
            }
        except Exception as e:
            return {
                "success": False,
                "result": None,
                "error": str(e),
                "execution_time": time.time() - start_time
            }
