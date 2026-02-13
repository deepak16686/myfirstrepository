"""
LLM Provider Factory

Returns the appropriate LLM integration based on the active provider
in the LLM registry. Backward compatible with all existing callers.
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
