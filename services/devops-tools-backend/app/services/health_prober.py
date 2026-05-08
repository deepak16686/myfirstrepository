"""
Health prober — issues probes against every tool in the registry, classifies
the result, and returns a typed HealthStatus.

Supported probe methods:
  * GET/POST/HEAD  — HTTP probe against `url_internal + health.path`.
  * tcp            — raw TCP connect test against `host:port` derived from
                     `url_internal` (or `health.port` override). Useful for
                     databases / queues that speak non-HTTP protocols.
  * docker_ps      — queries Docker Engine over the mounted UNIX socket and
                     classifies the container by its State.Status field.
  * docker_exec    — runs `health.command` inside `container_name` via the
                     Docker Engine exec API; classifies by exit code.

Classification rules (HTTP):
  * 2xx OR status ∈ expect_status     -> healthy
  * timeout / network error           -> down
  * >= 500                            -> down
  * other 3xx/4xx (unexpected)        -> degraded

Classification rules (tcp):
  * connect success within timeout    -> healthy
  * connect refused / timeout         -> down

Classification rules (docker_ps):
  * container State.Status == "running" AND Health is unset OR "healthy"
                                       -> healthy
  * container State.Status == "running" AND Health == "starting"
                                       -> degraded
  * container State.Status == "running" AND Health == "unhealthy"
                                       -> degraded
  * container State.Status != "running"
                                       -> down
  * container not found / socket not mounted
                                       -> unknown

Classification rules (docker_exec):
  * exit_code matches expect_exit_code -> healthy
  * any other exit_code                -> degraded
  * exec API failure / socket missing  -> unknown

Concurrency is bounded by an asyncio.Semaphore(10) to avoid stampeding the
local tool stack when we probe 30+ services every 30s.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from time import perf_counter
from typing import Iterable, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from app.services.tool_registry import HealthSpec, ToolSpec

log = logging.getLogger(__name__)

StatusLiteral = Literal["healthy", "degraded", "down", "unknown"]

# Path where Docker Desktop / Linux expose the Engine socket. Mounted into the
# backend container in docker-compose.yml. If missing, docker_* probes return
# "unknown" with a clear error instead of hard-failing.
DOCKER_SOCK_PATH = os.environ.get("DOCKER_SOCK_PATH", "/var/run/docker.sock")


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


def _parse_host_port(url: str, default_port: int | None = None) -> tuple[str, int] | None:
    """Pull (host, port) out of a URL like "postgres://ai-postgres:5432"
    or "redis://redis:6379/0" or "http://x:1234". Returns None on failure."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return None
    host = parsed.hostname
    port = parsed.port or default_port
    if not host or not port:
        # URL without an explicit port and no default — try to infer from scheme.
        scheme_defaults = {"http": 80, "https": 443, "postgres": 5432,
                           "postgresql": 5432, "redis": 6379, "mysql": 3306}
        port = scheme_defaults.get(parsed.scheme or "", None)
    if not host or not port:
        return None
    return host, port


# ---------------------------------------------------------------------------
# TCP probe — raw socket connect
# ---------------------------------------------------------------------------


async def _probe_tcp(tool: ToolSpec, timeout_seconds: float) -> HealthStatus:
    """Open a TCP connection to the tool's host:port and classify."""
    port = tool.health.port
    target = _parse_host_port(tool.url_internal, default_port=port)
    if target is None:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error="tcp probe: could not derive host:port from url_internal "
                  f"({tool.url_internal!r})",
        )

    host, resolved_port = target
    started = perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, resolved_port),
            timeout=timeout_seconds,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 - close errors don't affect the result
            pass
    except asyncio.TimeoutError:
        elapsed_ms = int((perf_counter() - started) * 1000)
        return HealthStatus(
            tool_id=tool.id,
            status="down",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"tcp timeout after {timeout_seconds}s connecting to "
                  f"{host}:{resolved_port}",
        )
    except OSError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        return HealthStatus(
            tool_id=tool.id,
            status="down",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"tcp connect failed: {exc}"[:200],
        )

    elapsed_ms = int((perf_counter() - started) * 1000)
    return HealthStatus(
        tool_id=tool.id,
        status="healthy",
        latency_ms=elapsed_ms,
        last_checked=_now(),
        http_status=None,
        error=None,
    )


# ---------------------------------------------------------------------------
# Docker Engine probes — via UNIX socket
# ---------------------------------------------------------------------------


def _docker_client() -> httpx.AsyncClient | None:
    """Return an httpx client wired to the Docker Engine UNIX socket,
    or None if the socket isn't mounted."""
    if not os.path.exists(DOCKER_SOCK_PATH):
        return None
    transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCK_PATH)
    # The "http://docker" base URL is a placeholder — httpx ignores the host
    # when dispatched through a UDS transport.
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://docker",
        timeout=5.0,
    )


async def _probe_docker_ps(tool: ToolSpec, timeout_seconds: float) -> HealthStatus:
    """Ask Docker Engine for the container's State and classify."""
    container = tool.container_name
    if not container:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error="docker_ps probe: tool has no container_name",
        )
    client = _docker_client()
    if client is None:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error=f"docker_ps: {DOCKER_SOCK_PATH} not mounted in backend",
        )

    started = perf_counter()
    try:
        async with client:
            resp = await client.get(f"/containers/{container}/json", timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((perf_counter() - started) * 1000)
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"docker_ps engine call failed: {exc}"[:200],
        )

    elapsed_ms = int((perf_counter() - started) * 1000)
    if resp.status_code == 404:
        return HealthStatus(
            tool_id=tool.id,
            status="down",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"container {container!r} not found",
        )
    if resp.status_code != 200:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"docker engine HTTP {resp.status_code}",
        )

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"docker_ps json parse: {exc}"[:200],
        )

    state = (data.get("State") or {})
    status = (state.get("Status") or "").lower()
    health = ((state.get("Health") or {}).get("Status") or "").lower()

    if status == "running":
        # Health may be unset (no HEALTHCHECK) which the Engine reports as "".
        if health in ("", "healthy"):
            cls: StatusLiteral = "healthy"
            err = None
        elif health == "starting":
            cls = "degraded"
            err = "container starting"
        else:
            cls = "degraded"
            err = f"container health={health!r}"
    else:
        cls = "down"
        err = f"container state={status!r}"

    return HealthStatus(
        tool_id=tool.id,
        status=cls,
        latency_ms=elapsed_ms,
        last_checked=_now(),
        http_status=None,
        error=err,
    )


async def _probe_docker_exec(tool: ToolSpec, timeout_seconds: float) -> HealthStatus:
    """Run `health.command` inside `container_name` via Docker exec."""
    container = tool.container_name
    cmd = tool.health.command
    if not container:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error="docker_exec probe: tool has no container_name",
        )
    if not cmd:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error="docker_exec probe: tool has no health.command",
        )
    client = _docker_client()
    if client is None:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            last_checked=_now(),
            error=f"docker_exec: {DOCKER_SOCK_PATH} not mounted in backend",
        )

    expected_exit = tool.health.expect_exit_code if tool.health.expect_exit_code is not None else 0

    started = perf_counter()
    try:
        async with client:
            # 1. Create exec instance
            create = await client.post(
                f"/containers/{container}/exec",
                json={"Cmd": cmd, "AttachStdout": False, "AttachStderr": False},
                timeout=timeout_seconds,
            )
            if create.status_code != 201:
                return HealthStatus(
                    tool_id=tool.id,
                    status="unknown",
                    latency_ms=int((perf_counter() - started) * 1000),
                    last_checked=_now(),
                    error=f"docker exec create HTTP {create.status_code}",
                )
            exec_id = create.json().get("Id")
            if not exec_id:
                return HealthStatus(
                    tool_id=tool.id,
                    status="unknown",
                    latency_ms=int((perf_counter() - started) * 1000),
                    last_checked=_now(),
                    error="docker exec create: no Id in response",
                )

            # 2. Start exec (detached=False required so the request blocks until done)
            start = await client.post(
                f"/exec/{exec_id}/start",
                json={"Detach": False, "Tty": False},
                timeout=timeout_seconds,
            )
            if start.status_code not in (200, 204, 101):
                return HealthStatus(
                    tool_id=tool.id,
                    status="unknown",
                    latency_ms=int((perf_counter() - started) * 1000),
                    last_checked=_now(),
                    error=f"docker exec start HTTP {start.status_code}",
                )

            # 3. Inspect to get ExitCode
            inspect = await client.get(f"/exec/{exec_id}/json", timeout=timeout_seconds)
            if inspect.status_code != 200:
                return HealthStatus(
                    tool_id=tool.id,
                    status="unknown",
                    latency_ms=int((perf_counter() - started) * 1000),
                    last_checked=_now(),
                    error=f"docker exec inspect HTTP {inspect.status_code}",
                )
            exit_code = inspect.json().get("ExitCode")
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((perf_counter() - started) * 1000)
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=f"docker_exec engine call failed: {exc}"[:200],
        )

    elapsed_ms = int((perf_counter() - started) * 1000)
    if exit_code is None:
        return HealthStatus(
            tool_id=tool.id,
            status="unknown",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error="docker exec returned null ExitCode (still running?)",
        )
    if exit_code == expected_exit:
        return HealthStatus(
            tool_id=tool.id,
            status="healthy",
            latency_ms=elapsed_ms,
            last_checked=_now(),
            error=None,
        )
    return HealthStatus(
        tool_id=tool.id,
        status="degraded",
        latency_ms=elapsed_ms,
        last_checked=_now(),
        error=f"exec exit_code={exit_code} (expected {expected_exit})",
    )


# ---------------------------------------------------------------------------
# Per-tool probe — dispatch
# ---------------------------------------------------------------------------


async def probe_tool(
    tool: ToolSpec,
    client: httpx.AsyncClient,
    timeout_seconds: float = 4.0,
) -> HealthStatus:
    """Probe a single tool and return a typed HealthStatus.

    Never raises — upstream exceptions are captured and classified.
    """
    method = (tool.health.method or "GET").lower()

    if method == "tcp":
        return await _probe_tcp(tool, timeout_seconds)
    if method == "docker_ps":
        return await _probe_docker_ps(tool, timeout_seconds)
    if method == "docker_exec":
        return await _probe_docker_exec(tool, timeout_seconds)

    # HTTP (default)
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
    http_method = method.upper()

    started = perf_counter()
    try:
        response = await client.request(
            method=http_method,
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
