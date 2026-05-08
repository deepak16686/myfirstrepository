"""
Shared in-memory store for live chat-tool phase updates.

Both ``chat_service`` and the pipeline generator can write phase
updates to this store, keyed by the client-provided ``request_id`` (or
``conversation_id`` as fallback). The chat router exposes it via
``GET /api/v1/chat/inflight/{key}`` so the frontend can poll while
its main ``POST /api/v1/chat/`` is still in flight and render a live
status card under the thinking dots:

    analyzing       → "Analyzing repo..."
    checking_rag    → "Checking RAG cache..."
    rag_hit         → "Template found in RAG. No LLM call."
    calling_llm     → "Calling Codex Code (gpt-5.5) to generate template..."
    fixer_attempt   → "Fixer attempt N/10..."
    llm_validated   → "Validated on first try."
    llm_fixed       → "LLM + auto-fixer converged after N/10 attempts."
    committing      → "Committing & starting pipeline..."
    monitoring      → "Pipeline running on branch X."
    validation_failed → "LLM fixer exhausted 10 attempts."

The store is intentionally a process-local dict — the backend runs as
a single uvicorn worker so that's enough; if we ever scale to multiple
workers we'll move this into Redis under the same key prefix that
``HealthCache`` uses.
"""
from typing import Any, Dict, Optional
import time

# key (request_id or conversation_id) -> phase payload
_STORE: Dict[str, Dict[str, Any]] = {}


def set_phase(
    key: Optional[str],
    phase: str,
    message: str,
    **extra: Any,
) -> None:
    """Push a phase update for the given chat request key.

    No-op when ``key`` is falsy so callers don't need to guard.
    """
    if not key:
        return
    payload: Dict[str, Any] = {
        "phase": phase,
        "message": message,
        "ts": time.time(),
    }
    payload.update({k: v for k, v in extra.items() if v is not None})
    _STORE[key] = payload


def get_phase(key: str) -> Optional[Dict[str, Any]]:
    """Return the most recent phase for ``key`` (or ``None`` if absent)."""
    return _STORE.get(key)


def clear_phase(key: Optional[str]) -> None:
    """Drop the phase entry — called by the chat router after the chat
    POST resolves so the next poll returns ``{"phase": "idle"}``."""
    if key:
        _STORE.pop(key, None)
