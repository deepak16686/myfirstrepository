"""
LLM Provider Factory

Returns the appropriate LLM integration based on configuration.
"""
from app.config import settings, tools_manager
from app.integrations.ollama import OllamaIntegration
from app.integrations.claude_code import ClaudeCodeIntegration


def get_llm_provider():
    """
    Factory that returns either OllamaIntegration or ClaudeCodeIntegration
    based on the LLM_PROVIDER setting.

    Both implement:
        async generate(model, prompt, system, context, options) -> {"response": "..."}
        async close()
    """
    if settings.llm_provider == "claude-code":
        return ClaudeCodeIntegration()
    else:
        ollama_config = tools_manager.get_tool("ollama")
        return OllamaIntegration(ollama_config)
