"""
Tool registry loader.

Parses `config/tools.yaml` (the canonical DevOps Portal tool registry) into
typed Pydantic models, with mtime-based caching so the file can be edited
in-place without restarting the backend.

Schema mirrors the actual YAML at `config/tools.yaml` v1, which supports:
  * HTTP probes:      health.method = "GET", path, expect_status (int | list[int])
  * Docker ps probes: health.method = "docker_ps", expect_status = "running"
  * Docker exec:      health.method = "docker_exec", command = [...],
                      expect_exit_code = int

Tools with empty `url_internal` (side-car containers like runners) are still
loaded — their health is resolved via the non-HTTP probe types.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models — exact mirror of config/tools.yaml schema_version: 1
# ---------------------------------------------------------------------------


class HealthSpec(BaseModel):
    """Per-tool health probe specification."""

    model_config = ConfigDict(extra="allow")

    method: Literal["GET", "POST", "HEAD", "tcp", "docker_ps", "docker_exec"] = "GET"
    path: str | None = None
    expect_status: int | list[int] | Literal["running"] | None = 200
    expect_exit_code: int | None = None
    command: list[str] | None = None
    # TCP probe: which port to connect to. When set, derived from url_internal
    # if omitted (e.g. "postgres://ai-postgres:5432" → port 5432).
    port: int | None = None

    @field_validator("expect_status", mode="before")
    @classmethod
    def _coerce_expect_status(cls, v: Any) -> Any:
        # YAML may emit single int or list; string "running" is valid for docker_ps
        if v is None:
            return v
        if isinstance(v, (int, list, str)):
            return v
        raise ValueError(f"expect_status must be int | list[int] | 'running', got {type(v).__name__}")


class ToolSpec(BaseModel):
    """One tool entry from `config/tools.yaml`."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    category: str
    description: str
    icon: str
    url_internal: str = ""
    url_external: str = ""
    # Public HTTPS URL exposed via Tailscale Funnel (internet-reachable).
    # Populated only for tools that consume one of the (limited) funnel slots.
    url_funnel: str | None = None
    # Tailnet-only HTTPS URL exposed via `tailscale serve` (reachable only by
    # devices logged into the owner's tailnet). Populated for every tool in
    # the registry; the public surface is a strict subset via url_funnel.
    url_tailnet: str | None = None
    health: HealthSpec = Field(default_factory=HealthSpec)
    credentials: str = "none"
    embed: bool = False
    tags: list[str] = Field(default_factory=list)
    compose_project: str | None = None
    container_name: str | None = None
    docs_url: str | None = None


class CategorySpec(BaseModel):
    """Category metadata for the portal UI."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    order: int = 999
    color: str | None = None


class Registry(BaseModel):
    """Full registry document."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = 1
    generated_at: date | str | None = None
    source_of_truth: str | None = None
    categories: list[CategorySpec] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Loader with mtime cache
# ---------------------------------------------------------------------------


class _RegistryCache:
    """Singleton cache keyed by (absolute path, mtime_ns)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._mtime_ns: int | None = None
        self._registry: Registry | None = None
        self._loaded_at: datetime | None = None

    def load(self, path: Path | str) -> Registry:
        """Load registry from YAML, using cached copy if the file is unchanged."""
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(
                f"Tool registry not found at {resolved}. "
                f"Create `config/tools.yaml` or set TOOLS_REGISTRY_PATH."
            )

        mtime_ns = resolved.stat().st_mtime_ns

        with self._lock:
            if (
                self._registry is not None
                and self._path == resolved
                and self._mtime_ns == mtime_ns
            ):
                return self._registry

            log.info(
                "Loading tool registry from %s (mtime_ns=%s)", resolved, mtime_ns
            )
            raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
            registry = Registry.model_validate(raw)

            # Detect duplicate IDs early — would break /tools/{id} lookup.
            ids = [t.id for t in registry.tools]
            dupes = {x for x in ids if ids.count(x) > 1}
            if dupes:
                raise ValueError(f"Duplicate tool IDs in registry: {sorted(dupes)}")

            self._path = resolved
            self._mtime_ns = mtime_ns
            self._registry = registry
            self._loaded_at = datetime.now()
            return registry

    def invalidate(self) -> None:
        with self._lock:
            self._path = None
            self._mtime_ns = None
            self._registry = None
            self._loaded_at = None


_cache = _RegistryCache()


def load_registry(path: Path | str) -> Registry:
    """Public entry point — loads + caches the registry.

    Re-reads from disk if mtime changed; otherwise returns cached copy.
    Raises FileNotFoundError if the file is missing, ValueError if invalid.
    """
    return _cache.load(path)


def invalidate_registry_cache() -> None:
    """Drop the cached registry. Primarily for tests."""
    _cache.invalidate()


def get_tool_by_id(registry: Registry, tool_id: str) -> ToolSpec | None:
    """Return the ToolSpec for the given id, or None if unknown."""
    for tool in registry.tools:
        if tool.id == tool_id:
            return tool
    return None
