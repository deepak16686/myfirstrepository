"""
File: llm_registry.py
Purpose: Central registry that manages all available LLM providers (Ollama, Claude Code CLI, OpenAI)
         with metadata (name, description, models, status) and supports runtime switching between
         providers via set_active_provider(). Singleton instance used throughout the application.
When Used: Instantiated once at import time. Queried by llm_provider.py on every LLM call. Modified
           by the llm_settings router when users switch providers via the frontend.
Why Created: Supports multiple LLM backends with runtime switching so users can compare providers
             without restarting the backend. Replaces the original simple if/else factory.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from app.config import settings, tools_manager


@dataclass
class LLMProviderInfo:
    """Metadata about a single LLM provider."""
    id: str
    name: str
    description: str
    models: List[str]
    default_model: str
    enabled: bool = False
    active_model: Optional[str] = None  # currently selected model (overrides default)

    @property
    def display_name(self) -> str:
        model = self.active_model or self.default_model
        return f"{self.name} ({model})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "models": self.models,
            "default_model": self.default_model,
            "active_model": self.active_model or self.default_model,
            "enabled": self.enabled,
        }


class LLMProviderRegistry:
    """Manages available LLM providers and runtime switching."""

    def __init__(self):
        self._providers: Dict[str, LLMProviderInfo] = {}
        self._active_provider_id: str = settings.llm_provider
        self._initialize_providers()

    def _initialize_providers(self):
        """Register all known providers with metadata."""
        # Ollama — always available (local)
        self._providers["ollama"] = LLMProviderInfo(
            id="ollama",
            name="Ollama",
            description="Local LLM via Ollama (qwen3:32b, llama3, etc.)",
            models=["pipeline-generator-v5", "qwen3:32b", "llama3.1:70b"],
            default_model="pipeline-generator-v5",
            enabled=True,
        )

        # Claude Code CLI
        self._providers["claude-code"] = LLMProviderInfo(
            id="claude-code",
            name="Claude Code",
            description="Anthropic Claude via CLI (Opus, Sonnet, Haiku)",
            models=["opus", "sonnet", "haiku"],
            default_model=settings.claude_model or "opus",
            enabled=True,  # CLI is always installed in container
        )

        # OpenAI
        self._providers["openai"] = LLMProviderInfo(
            id="openai",
            name="OpenAI",
            description="OpenAI API (GPT-4, GPT-4 Turbo, GPT-3.5)",
            models=["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
            default_model="gpt-4",
            enabled=bool(settings.openai_api_key),
        )

    def list_providers(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all providers with metadata."""
        providers = []
        for p in self._providers.values():
            if enabled_only and not p.enabled:
                continue
            info = p.to_dict()
            info["is_active"] = (p.id == self._active_provider_id)
            providers.append(info)
        return providers

    def get_active_provider_id(self) -> str:
        return self._active_provider_id

    def get_active_provider_info(self) -> Optional[LLMProviderInfo]:
        return self._providers.get(self._active_provider_id)

    def get_active_display_name(self) -> str:
        """Human-readable name like 'Claude Code (opus)'."""
        info = self.get_active_provider_info()
        return info.display_name if info else "Unknown LLM"

    def set_active_provider(self, provider_id: str, model: str = None) -> Dict[str, Any]:
        """Switch the active provider at runtime."""
        if provider_id not in self._providers:
            raise ValueError(f"Unknown provider: {provider_id}")

        provider = self._providers[provider_id]
        if not provider.enabled:
            raise ValueError(f"Provider '{provider_id}' is not enabled (missing API key or config)")

        if model:
            if model not in provider.models:
                raise ValueError(
                    f"Model '{model}' not available for {provider.name}. "
                    f"Available: {provider.models}"
                )
            provider.active_model = model

        self._active_provider_id = provider_id
        return {
            "success": True,
            "active_provider": provider_id,
            "active_display_name": provider.display_name,
        }

    def create_provider_instance(self, provider_id: str = None):
        """Factory: create a provider instance. Defaults to active provider."""
        pid = provider_id or self._active_provider_id

        if pid == "claude-code":
            from app.integrations.claude_code import ClaudeCodeIntegration
            return ClaudeCodeIntegration()
        elif pid == "openai":
            from app.integrations.openai_integration import OpenAIIntegration
            return OpenAIIntegration()
        else:
            # Ollama (default fallback)
            from app.integrations.ollama import OllamaIntegration
            ollama_config = tools_manager.get_tool("ollama")
            return OllamaIntegration(ollama_config)

    def get_provider_info(self, provider_id: str) -> Optional[LLMProviderInfo]:
        return self._providers.get(provider_id)


# Singleton instance
llm_registry = LLMProviderRegistry()
