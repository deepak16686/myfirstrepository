"""
File: claude_code.py
Purpose: LLM provider that invokes the Claude Code CLI as a subprocess to generate pipeline YAML,
         Dockerfiles, and Terraform configs. Implements the same generate() interface as Ollama
         so it can be swapped in transparently via the LLM registry.
When Used: When LLM_PROVIDER is set to 'claude-code'. Called by pipeline generators, LLM fixers,
           and the terraform generator to get LLM responses from Claude (Sonnet/Opus) instead of
           local Ollama models. The CLI binary runs inside the backend Docker container.
Why Created: Provides access to Anthropic's Claude models as an alternative to local Ollama inference,
             enabling higher-quality pipeline generation without requiring a GPU. Uses the CLI
             approach (not API) because the Claude Code CLI handles auth via mounted .claude directory.
"""
import asyncio
import json
import os
import logging
from typing import Dict, Any, Optional, List

from app.config import settings

logger = logging.getLogger(__name__)


class ClaudeCodeIntegration:
    """
    Claude Code CLI integration.

    Calls `claude -p "prompt" --output-format json` as an async subprocess.
    Parses the JSON output and returns a dict matching Ollama's response format:
        {"response": "...text..."}
    """

    def __init__(self):
        self.model = settings.claude_model
        self.timeout = settings.claude_timeout
        self._system_prompt_cache: Optional[str] = None

    def _load_system_prompt(self) -> str:
        """Load the pipeline system prompt extracted from the Modelfile."""
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
        Generate a completion using Claude Code CLI.

        Returns dict with {"response": "..."} matching Ollama format.
        The model/context/options params are accepted for interface
        compatibility but ignored (Claude uses settings.claude_model).
        """
        # Build the full prompt with system prompt prepended
        full_prompt = ""

        # Use provided system prompt, or load from file
        sys_prompt = system or self._load_system_prompt()
        if sys_prompt:
            full_prompt = f"<system>\n{sys_prompt}\n</system>\n\n"

        full_prompt += prompt

        # Build CLI command
        cmd = [
            "claude",
            "-p", full_prompt,
            "--output-format", "json",
            "--model", self.model,
            "--max-turns", "1",
        ]

        logger.info(
            f"Calling Claude Code CLI (model={self.model}, "
            f"prompt_length={len(full_prompt)})"
        )

        raw_output = ""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(
                    f"Claude CLI failed (exit {process.returncode}): "
                    f"{error_msg[:500]}"
                )
                raise RuntimeError(
                    f"Claude CLI exited with code {process.returncode}: "
                    f"{error_msg[:500]}"
                )

            # Parse JSON output
            raw_output = stdout.decode("utf-8", errors="replace")
            result = json.loads(raw_output)

            # Claude CLI JSON: {"type": "result", "result": "text content"}
            text_response = result.get("result", "")

            logger.info(
                f"Claude CLI response received "
                f"(length={len(text_response)})"
            )

            # Return in Ollama-compatible format
            return {"response": text_response}

        except asyncio.TimeoutError:
            logger.error(f"Claude CLI timed out after {self.timeout}s")
            raise RuntimeError(
                f"Claude CLI timed out after {self.timeout} seconds"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude CLI JSON output: {e}")
            return {"response": raw_output.strip() if raw_output else ""}

    async def close(self):
        """No-op for compatibility with OllamaIntegration pattern."""
        pass
