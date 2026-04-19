"""
Health prober — issues HTTP probes (and best-effort docker checks) against
every tool in the registry, classifies the result, and returns a typed
HealthStatus.

Classification rules (HTTP):
  * 2xx OR status ∈ expect_status     -> healthy
  * timeout / network error            -> down
  * >= 500                             -> down
  * other 3xx/4xx (unexpected)         -> degraded

Non-HTTP probe types (`docker_ps`, `docker_exec`) cannot be executed from
inside the backend without the Docker socket. For those tools we record an
"unknown" status — the portal UI reads this as a neutral state and a future
iteration can shell out to the docker CLI if the socket is mounted.

Concurrency is bounded by an asyncio.Semaphore(10) to avoid stampeding the
local tool stack when we probe 30+ services every 30s.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Iterable, Literal

import httpx
from pydantic import BaseModel

from app.services.tool_registry import HealthSpec, ToolSpec

log = logging.getLogger(__name__)

StatusLiteral = Literal["healthy", "degraded", "down", "unknown"]


class HealthStatus(BaseModel):
    """Live health record for a single tool."""

    tool_id: str
    status: StatusLiteral
    latency_ms: int | None = None
    last_checked: datetime | None = None
    http_status: int | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _status_matches(actual: int, expected: int | list[int] | str | None) -> bool:
    """True if `actual` satisfies the `expect_status` spec."""
    if expected is None:
        return 200 <= actual < 300
    if isinstance(expected, int):
        return actual == expected
    if isinstance(expected, list):
        return actual in expected
    # string form ("running") doesn't apply to HTTP status
    return False


def _classify_http(actual: int, spec: HealthSpec) -> StatusLiteral:
    if _status_matches(actual, spec.expect_status):
        return "healthy"
    if actual >= 500:
        return "down"
    # 2xx that didn't match expected, or 3xx/4xx — degraded
    return "degraded"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Per-tool probe
# ---------------------------------------------------------------------------


async def probe_tool(
    tool: ToolSpec,
    client: httpx.AsyncClient,
    timeout_seconds: float = 4.0,
) -> HealthStatus:
    """Probe a single tool and return a typed HealthStatus.

    Never raises — upstream exceptions are captured and classified.
    """
    method = tool.health.method.upper() if tool.health.method else "GET"

    # Non-HTTP probe types — we can't run docker from here, so mark unknown.
    if method in {"DOCKER_PS", "DOCKER_EXEC"}:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error=f"probe method '{tool.health.method}' requires docker socket (not wired)",
        )

    if not tool.url_internal:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error="no url_internal configured",
        )

    path = tool.health.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    url = f"{tool.url_internal.rstrip('/')}{path}"

    started = perf_counter()
    try:
        response = await client.request(
            method=method,
            url=url,
            timeout=timeout_seconds,
            follow_redirects=True,
        )
    except httpx.TimeoutException as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        log.debug("probe timeout tool_id=%s url=%s err=%s", tool.id, url, exc)
        return HealthStatus(
            tool_id=tool.id,
            status="down",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"timeout after {timeout_seconds}s",
        )
    except httpx.HTTPError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        log.debug("probe network err tool_id=%s url=%s err=%s", tool.id, url, exc)
        return HealthStatus(
            tool_id=tool.id,
            status="down",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=str(exc)[:200],
        )
    except Exception as exc:  # noqa: BLE001 - defensive
        elapsed_ms = int((perf_counter() - started) * 1000)
        log.warning("probe unexpected err tool_id=%s url=%s", tool.id, url, exc_info=exc)
        return HealthStatus(
            tool_id=tool.id,
            status="down",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"{type(exc).__name__}: {exc}"[:200],
        )

    elapsed_ms = int((perf_counter() - started) * 1000)
    status_cls = _classify_http(response.status_code, tool.health)
    return HealthStatus(
        tool_id=tool.id,
        status=status_cls,
        latency_ms=elapsed_ms,
        last_checked=_now(),
        http_status=response.status_code,
        error=None if status_cls == "healthy" else f"HTTP {response.status_code}",
    )


# ---------------------------------------------------------------------------
# Bulk probe — bounded concurrency
# ---------------------------------------------------------------------------


async def probe_all(
    tools: Iterable[ToolSpec],
    client: httpx.AsyncClient,
    timeout_seconds: float = 4.0,
    max_concurrent: int = 10,
) -> dict[str, HealthStatus]:
    """Probe every tool concurrently; return {tool_id: HealthStatus}."""
    tools_list = list(tools)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(tool: ToolSpec) -> HealthStatus:
        async with semaphore:
            return await probe_tool(tool, client, timeout_seconds=timeout_seconds)

    results = await asyncio.gather(
        *(_bounded(t) for t in tools_list), return_exceptions=True
    )

    out: dict[str, HealthStatus] = {}
    for tool, res in zip(tools_list, results):
        if isinstance(res, BaseException):
            log.warning("probe_all exception tool_id=%s", tool.id, exc_info=res)
            out[tool.id] = HealthStatus(
                tool_id=tool.id,
                status="unknown",
                last_checked=_now(),
                error=f"{type(res).__name__}: {res}"[:200],
            )
        else:
            out[tool.id] = res
    return out
