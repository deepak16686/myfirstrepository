"""
OpenAI API Integration

Calls the OpenAI-compatible API to generate LLM responses.
Designed as a drop-in replacement matching Ollama/Claude interface:
    async generate(model, prompt, system, context, options) -> {"response": "..."}
    async close()
"""
import os
import logging
from typing import Dict, Any, Optional, List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OpenAIIntegration:
    """
    OpenAI API integration.

    Calls the OpenAI chat completions endpoint and returns a dict
    matching Ollama's response format: {"response": "...text..."}
    """

    def __init__(self):
        self.api_key = settings.openai_api_key
        self.base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.timeout = settings.openai_timeout or 300
        self.client = httpx.AsyncClient(timeout=self.timeout)
        self._system_prompt_cache: Optional[str] = None

    def _load_system_prompt(self) -> str:
        """Load the pipeline system prompt (shared with Claude)."""
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "pipeline_system_prompt.txt"
        )
        try:
            with open(prompt_path, "r") as f:
                self._system_prompt_cache = f.read()
        except FileNotFoundError:
            logger.warning(f"System prompt file not found: {prompt_path}")
            self._system_prompt_cache = ""

        return self._system_prompt_cache

    async def generate(
        self,
        model: str = None,
        prompt: str = "",
        system: Optional[str] = None,
        context: Optional[List[int]] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a completion using OpenAI API.

        Returns dict with {"response": "..."} matching Ollama format.
        """
        model = model or "gpt-4"
        opts = options or {}
        temperature = opts.get("temperature", 0.2)

        # Build messages
        messages = []
        sys_prompt = system or self._load_system_prompt()
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(
            f"Calling OpenAI API (model={model}, "
            f"prompt_length={len(prompt)})"
        )

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 8192
                }
            )
            response.raise_for_status()
            data = response.json()

            text_response = data["choices"][0]["message"]["content"]
            logger.info(f"OpenAI response received (length={len(text_response)})")

            return {"response": text_response}

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAI API error: {e.response.status_code} - {e.response.text[:500]}")
            raise RuntimeError(f"OpenAI API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
