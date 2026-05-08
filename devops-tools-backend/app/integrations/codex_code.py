"""
Codex Code CLI Integration

Calls the OpenAI Codex CLI as a subprocess to generate LLM responses.
Designed as a drop-in replacement for OllamaIntegration.generate().
"""
import asyncio
import os
import logging
import tempfile
from typing import Dict, Any, Optional, List

from app.config import settings

logger = logging.getLogger(__name__)


class CodexCodeIntegration:
    """
    Codex CLI integration.

    Calls `codex exec` non-interactively and reads the last assistant message
    from a temporary output file. Returns a dict matching Ollama's response
    format: {"response": "...text..."}.
    """

    def __init__(self):
        self.model = settings.codex_model
        self.timeout = settings.codex_timeout
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
            with open(prompt_path, "r", encoding="utf-8") as f:
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
        Generate a completion using Codex CLI.

        The model/context/options params are accepted for interface
        compatibility. The backend may pass Ollama model names such as
        ``pipeline-generator-v5``; Codex must use ``CODEX_MODEL`` instead.
        """
        selected_model = self.model
        full_prompt = ""

        sys_prompt = system or self._load_system_prompt()
        if sys_prompt:
            full_prompt = f"<system>\n{sys_prompt}\n</system>\n\n"
        full_prompt += prompt

        output_file = tempfile.NamedTemporaryFile(delete=False)
        output_path = output_file.name
        output_file.close()

        cmd = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-rules",
            "--ignore-user-config",
            "--output-last-message",
            output_path,
        ]
        if selected_model:
            cmd.extend(["--model", selected_model])
        cmd.append("-")

        logger.info(
            f"Calling Codex CLI (model={selected_model or 'default'}, "
            f"prompt_length={len(full_prompt)})"
        )

        raw_stdout = ""
        raw_stderr = ""
        try:
            env = os.environ.copy()
            env.setdefault("CODEX_HOME", "/root/.codex")
            env.setdefault("IS_SANDBOX", "1")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(full_prompt.encode("utf-8")),
                timeout=self.timeout,
            )
            raw_stdout = stdout.decode("utf-8", errors="replace")
            raw_stderr = stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                logger.error(
                    f"Codex CLI failed (exit {process.returncode}): "
                    f"{raw_stderr[:500]}"
                )
                raise RuntimeError(
                    f"Codex CLI exited with code {process.returncode}: "
                    f"{raw_stderr[:500]}"
                )

            with open(output_path, "r", encoding="utf-8") as f:
                text_response = f.read().strip()
            if not text_response:
                text_response = raw_stdout.strip()

            logger.info(
                f"Codex CLI response received "
                f"(length={len(text_response)})"
            )
            return {"response": text_response}

        except asyncio.TimeoutError:
            logger.error(f"Codex CLI timed out after {self.timeout}s")
            raise RuntimeError(
                f"Codex CLI timed out after {self.timeout} seconds"
            )
        finally:
            try:
                os.unlink(output_path)
            except OSError:
                pass

    async def close(self):
        """No-op for compatibility with OllamaIntegration pattern."""
        pass
