"""
File: llm_settings.py
Purpose: Exposes REST endpoints for listing all configured LLM providers (Ollama, Claude Code CLI),
    switching the active provider at runtime, and querying which provider is currently in use for
    pipeline generation and chat.
When Used: Invoked by the frontend LLM Settings panel to display available providers, let the
    user toggle between Ollama and Claude Code, and show the active provider status via the
    /llm/* routes.
Why Created: Decouples LLM provider management from the pipeline generators so that switching
    between Ollama and Claude Code CLI can happen at runtime without restarting the backend or
    modifying environment variables.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.integrations.llm_registry import llm_registry

router = APIRouter(prefix="/llm", tags=["LLM Settings"])


class SetActiveProviderRequest(BaseModel):
    provider_id: str
    model: Optional[str] = None


@router.get("/providers")
async def list_providers(enabled_only: bool = False):
    """List all configured LLM providers with their metadata and active state."""
    providers = llm_registry.list_providers(enabled_only=enabled_only)
    active = llm_registry.get_active_provider_info()
    return {
        "providers": providers,
        "active_provider": llm_registry.get_active_provider_id(),
        "active_display_name": active.display_name if active else "Unknown",
    }


@router.post("/set-active")
async def set_active_provider(request: SetActiveProviderRequest):
    """Switch the active LLM provider at runtime."""
    try:
        result = llm_registry.set_active_provider(
            provider_id=request.provider_id,
            model=request.model
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/active")
async def get_active_provider():
    """Get the currently active LLM provider details."""
    info = llm_registry.get_active_provider_info()
    if not info:
        raise HTTPException(status_code=500, detail="No active LLM provider configured")
    return {
        "provider": info.to_dict(),
        "display_name": info.display_name,
    }
