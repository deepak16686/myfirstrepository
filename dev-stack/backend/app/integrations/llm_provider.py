"""
File: llm_provider.py
Purpose: Factory functions that return the appropriate LLM integration instance (Ollama, Claude Code,
         or OpenAI) based on the currently active provider in the LLM registry. Provides backward-
         compatible get_llm_provider() and get_active_provider_name() entry points.
When Used: Called by every pipeline generator, LLM fixer, terraform generator, and chat service whenever
           they need to invoke LLM inference. The factory delegates to llm_registry to determine which
           provider is currently active.
Why Created: Decouples LLM consumer code from specific providers so callers can import get_llm_provider()
             without knowing whether Ollama, Claude, or OpenAI is active.
"""
from app.integrations.llm_registry import llm_registry


def get_llm_provider(provider_id: str = None):
    """
    Factory that returns the active LLM provider instance.

    All providers implement:
        async generate(model, prompt, system, context, options) -> {"response": "..."}
        async close()
    """
    return llm_registry.create_provider_instance(provider_id)


def get_active_provider_name() -> str:
    """Get the display name of the active LLM provider (e.g. 'Claude Code (opus)')."""
    return llm_registry.get_active_display_name()
