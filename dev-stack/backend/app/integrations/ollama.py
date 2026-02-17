"""
Ollama LLM API Integration
"""
from typing import List, Optional, Dict, Any, AsyncGenerator
import json
import httpx
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class OllamaIntegration(BaseIntegration):
    """Ollama LLM API integration"""

    # LLM generation can take a long time
    GENERATION_TIMEOUT = 300.0  # 5 minutes

    def __init__(self, config: ToolConfig):
        super().__init__(config)
        # Override the client with a longer timeout for LLM operations
        self.client = httpx.AsyncClient(timeout=self.GENERATION_TIMEOUT)

    @property
    def name(self) -> str:
        return "ollama"

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/api/version")
            if response.status_code == 200:
                data = response.json()
                return data.get("version")
        except Exception:
            pass
        return None

    # ========================================================================
    # Models
    # ========================================================================

    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models"""
        response = await self.get("/api/tags")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])

    async def get_model_info(self, model: str) -> Dict[str, Any]:
        """Get information about a specific model"""
        response = await self.post("/api/show", json={"name": model})
        response.raise_for_status()
        return response.json()

    async def pull_model(self, model: str) -> Dict[str, Any]:
        """Pull a model from the registry"""
        response = await self.post("/api/pull", json={"name": model})
        response.raise_for_status()
        return response.json()

    async def delete_model(self, model: str) -> bool:
        """Delete a model"""
        response = await self.delete("/api/delete", json={"name": model})
        return response.status_code == 200

    # ========================================================================
    # Generation
    # ========================================================================

    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        context: Optional[List[int]] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate a completion (non-streaming)"""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        if system:
            payload["system"] = system
        if context:
            payload["context"] = context
        if options:
            payload["options"] = options

        response = await self.post("/api/generate", json=payload)
        response.raise_for_status()
        # FIX: Handle None response and return empty dict as fallback
        return response.json() or {}

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Chat completion (non-streaming)"""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        if system:
            # Insert system message at the beginning
            payload["messages"] = [{"role": "system", "content": system}] + messages
        if options:
            payload["options"] = options

        response = await self.post("/api/chat", json=payload)
        response.raise_for_status()
        # FIX: Handle None response and return empty dict as fallback
        return response.json() or {}

    # ========================================================================
    # Embeddings
    # ========================================================================

    async def embed(
        self,
        model: str,
        input: str | List[str]
    ) -> Dict[str, Any]:
        """Generate embeddings"""
        payload = {
            "model": model,
            "input": input if isinstance(input, list) else [input]
        }

        response = await self.post("/api/embed", json=payload)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Running Models
    # ========================================================================

    async def list_running_models(self) -> List[Dict[str, Any]]:
        """List currently running models"""
        response = await self.get("/api/ps")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])
