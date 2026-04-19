"""
Portal router — unifies every locally-hosted DevOps tool behind a single API.

Endpoints (all under /api/v1/portal):
  GET  /tools                              — enriched catalog (with cached live health)
  GET  /tools/{tool_id}                    — single tool detail
  GET  /tools/{tool_id}/credentials        — operator-only: raw fields from Vault
  GET  /health                             — aggregate health map (from cache)
  GET  /health/{tool_id}                   — force re-probe, bypass cache
  GET  /categories                         — category meta + tool counts + healthy %
  POST /launch/{tool_id}                   — prepares a launch (returns redirect URL)
  GET  /stats                              — dashboard KPIs
  GET  /tailscale/status                   — tailnet state (best-effort, never raises)

The `credentials` field on `/tools` and `/tools/{id}` is **always** redacted
to `"<redacted>"` or `"none"`; the only way to fetch the raw pointer value is
the operator-guarded `/tools/{id}/credentials` endpoint, which reads from
HashiCorp Vault using the token configured on the backend (never shared
with the caller).
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import shutil
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.integrations.redis_client import HealthCache
from app.integrations.vault import VaultClient, VaultError
from app.services.health_prober import HealthStatus, probe_all, probe_tool
from app.services.tool_registry import (
    HealthSpec,
    Registry,
    ToolSpec,
    get_tool_by_id,
    load_registry,
)

log = logging.getLogger(__name__)
# Dedicated logger for credential fetches. Stays separate from `portal.*`
# diagnostics so operators can route it to a different sink/file if desired
# (e.g. append-only audit log at INFO).
audit_log = logging.getLogger("portal.audit")

router = APIRouter(prefix="/portal", tags=["portal"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ToolOut(BaseModel):
    """Public tool record — `credentials` is redacted, never emitted verbatim."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    category: str
    description: str
    icon: str
    url_internal: str = ""
    url_external: str = ""
    # Public internet URL via Tailscale Funnel (None for tailnet-only tools).
    url_funnel: str | None = None
    # Tailnet-only HTTPS URL via tailscale serve (present for every tool).
    url_tailnet: str | None = None
    health_spec: HealthSpec = Field(default_factory=HealthSpec)
    credentials: str = "none"
    embed: bool = False
    tags: list[str] = Field(default_factory=list)
    compose_project: str | None = None
    container_name: str | None = None
    docs_url: str | None = None
    health: HealthStatus | None = None


class CategoryOut(BaseModel):
    """Category with derived counts."""

    id: str
    name: str
    order: int
    color: str | None = None
    tool_count: int
    healthy_count: int
    healthy_pct: float


class LaunchResponse(BaseModel):
    redirect_url: str
    requires_auth: bool
    tool_id: str


class StatsResponse(BaseModel):
    total: int
    healthy: int
    degraded: int
    down: int
    unknown: int
    by_category: dict[str, dict[str, int]]
    generated_at: datetime


class TailscaleStatus(BaseModel):
    state: Literal["live", "local", "down"]
    hostname: str | None = None
    funnel_enabled: bool = False
    magic_dns: str | None = None
    error: str | None = None


class CredentialsOut(BaseModel):
    """Operator-only credentials payload for a single tool.

    ``fields`` contains the raw KV v2 values pulled from Vault. The portal
    never persists this response anywhere; it is emitted once per successful
    operator request and then discarded.
    """

    model_config = ConfigDict(extra="ignore")

    tool_id: str
    source: str
    fields: dict[str, str]
    retrieved_at: datetime


# ---------------------------------------------------------------------------
# Credentials redaction
# ---------------------------------------------------------------------------


def _redact_credentials(raw: str | None) -> str:
    """Collapse any credentials pointer to a fixed token.

    The raw string in tools.yaml is a pointer (e.g. `vault:secret/...`), never
    the secret itself, but we still never echo it back — the portal UI doesn't
    need it, only the operator does.
    """
    if not raw or raw.lower() == "none":
        return "none"
    return "<redacted>"


def _tool_to_out(tool: ToolSpec, health: HealthStatus | None) -> ToolOut:
    payload = tool.model_dump()
    payload["credentials"] = _redact_credentials(payload.get("credentials"))
    # The ToolSpec has a `health` (HealthSpec) field; we rename it to
    # `health_spec` in the output and populate `health` with the live status.
    payload["health_spec"] = payload.pop("health", HealthSpec().model_dump())
    payload["health"] = health.model_dump() if health else None
    return ToolOut.model_validate(payload)


# ---------------------------------------------------------------------------
# Registry + cache access helpers
# ---------------------------------------------------------------------------


def _registry() -> Registry:
    """Load (or re-load on mtime change) the tool registry."""
    return load_registry(settings.tools_registry_path)


def _health_cache(request: Request) -> HealthCache:
    cache = getattr(request.app.state, "portal_health_cache", None)
    if cache is None:
        # Fallback: create a dead cache that is pure in-memory. This shouldn't
        # happen in production — lifespan wires it — but keeps unit tests
        # resilient.
        cache = HealthCache(
            redis_url=settings.redis_url,
            default_ttl_seconds=settings.health_cache_ttl_seconds,
        )
        request.app.state.portal_health_cache = cache
    return cache


def _http_client(request: Request) -> httpx.AsyncClient:
    client = getattr(request.app.state, "portal_http_client", None)
    if client is None:
        client = httpx.AsyncClient(timeout=settings.health_probe_timeout_seconds)
        request.app.state.portal_http_client = client
    return client


async def _load_health_map(cache: HealthCache, tools: list[ToolSpec]) -> dict[str, HealthStatus]:
    """Pull per-tool health from the snapshot blob, falling back to per-key."""
    snapshot = await cache.get_json("portal:health:all")
    out: dict[str, HealthStatus] = {}
    if isinstance(snapshot, dict):
        for tool_id, raw in snapshot.items():
            try:
                out[tool_id] = HealthStatus.model_validate(raw)
            except Exception as exc:  # noqa: BLE001
                log.debug("snapshot parse err tool_id=%s err=%s", tool_id, exc)

    for t in tools:
        if t.id in out:
            continue
        raw = await cache.get_json(f"portal:health:{t.id}")
        if raw is not None:
            try:
                out[t.id] = HealthStatus.model_validate(raw)
            except Exception as exc:  # noqa: BLE001
                log.debug("per-key parse err tool_id=%s err=%s", t.id, exc)
    return out


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/tools",
    response_model=list[ToolOut],
    summary="List all tools with live health",
)
async def list_tools(request: Request) -> list[ToolOut]:
    """Return the full tool catalog, each enriched with the most recent
    cached HealthStatus (may be `null` if the first probe has not run)."""
    registry = _registry()
    cache = _health_cache(request)
    health_map = await _load_health_map(cache, registry.tools)

    return [_tool_to_out(t, health_map.get(t.id)) for t in registry.tools]


@router.get(
    "/tools/{tool_id}",
    response_model=ToolOut,
    summary="Get a single tool by id",
)
async def get_tool(tool_id: str, request: Request) -> ToolOut:
    registry = _registry()
    tool = get_tool_by_id(registry, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool '{tool_id}' not found")
    cache = _health_cache(request)
    raw = await cache.get_json(f"portal:health:{tool_id}")
    health = HealthStatus.model_validate(raw) if raw else None
    return _tool_to_out(tool, health)


# ---------------------------------------------------------------------------
# Operator-only credentials endpoint
# ---------------------------------------------------------------------------


_VAULT_POINTER_PREFIX = "vault:"


def _operator_header_value(request: Request) -> str | None:
    """Fetch the operator header value (case-insensitive name)."""
    header_name = settings.portal_operator_header or "X-Portal-Operator"
    # Starlette / FastAPI Headers are case-insensitive; .get handles both
    # canonical and lower-case forms.
    return request.headers.get(header_name)


def _truncate_ua(ua: str | None, limit: int = 80) -> str:
    if not ua:
        return "-"
    return ua[:limit]


@router.get(
    "/tools/{tool_id}/credentials",
    response_model=CredentialsOut,
    responses={
        204: {"description": "Tool has no credentials (credentials: none)"},
        400: {"description": "Unsupported credentials pointer scheme"},
        401: {"description": "Missing operator header"},
        403: {"description": "Operator token mismatch"},
        404: {"description": "Tool not found"},
        503: {"description": "Vault or operator token not configured, or Vault unreachable"},
    },
    summary="Operator-only: fetch raw credentials for a tool from Vault",
)
async def get_tool_credentials(
    tool_id: str,
    request: Request,
    response: Response,
) -> CredentialsOut | Response:
    """Fetch raw credentials for a tool from Vault.

    Guards (in order):
      1. operator token configured on the backend       → else 503
      2. Vault client wired on app.state                → else 503
      3. request carries the operator header            → else 401
      4. header value matches (hmac.compare_digest)     → else 403
      5. tool exists in the registry                    → else 404
      6. tool has credentials (not ``none`` / empty)    → else 204
      7. pointer starts with ``vault:``                 → else 400
      8. Vault read succeeds                            → else 503

    Never logs the ``fields`` values or the operator token.
    """
    # --- 1 & 2: endpoint enabled? ---------------------------------------
    operator_token = settings.portal_operator_token or ""
    vault_client: VaultClient | None = getattr(request.app.state, "vault_client", None)
    if not operator_token or vault_client is None:
        raise HTTPException(
            status_code=503,
            detail="credentials endpoint disabled: vault or operator token not configured",
        )

    # --- 3 & 4: operator auth ------------------------------------------
    provided = _operator_header_value(request)
    if provided is None:
        raise HTTPException(
            status_code=401,
            detail=f"missing operator header '{settings.portal_operator_header}'",
        )
    # Constant-time compare over bytes to avoid timing side-channels.
    if not hmac.compare_digest(
        provided.encode("utf-8"),
        operator_token.encode("utf-8"),
    ):
        raise HTTPException(status_code=403, detail="operator token mismatch")

    # --- 5: tool lookup ------------------------------------------------
    registry = _registry()
    tool = get_tool_by_id(registry, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool '{tool_id}' not found")

    # --- 6: credentials pointer present? -------------------------------
    raw_pointer = (tool.credentials or "").strip()
    if not raw_pointer or raw_pointer.lower() == "none":
        # 204 — let the client render a "no credentials on this tool" state.
        response.status_code = 204
        return Response(status_code=204)

    # --- 7: scheme check ------------------------------------------------
    if not raw_pointer.startswith(_VAULT_POINTER_PREFIX):
        raise HTTPException(status_code=400, detail="unsupported credentials pointer scheme")

    vault_path = raw_pointer[len(_VAULT_POINTER_PREFIX) :]

    # --- 8: read from Vault --------------------------------------------
    try:
        fields = await vault_client.read_kv(vault_path)
    except VaultError as exc:
        # Never leak the pointer's write-side value — just status & path.
        log.warning(
            "vault_read_failed tool_id=%s source=%s status=%s msg=%s",
            tool.id,
            raw_pointer,
            exc.status_code,
            exc.message,
        )
        # 403/404 from Vault surface as 503 to the caller — we don't want to
        # imply the operator doesn't have access; the portal controls access.
        raise HTTPException(
            status_code=503,
            detail=f"vault read failed ({exc.status_code}): {exc.message}",
        ) from exc

    retrieved_at = datetime.now(timezone.utc)

    # Audit log — metadata only, values never touched.
    requester_ip = request.client.host if request.client else "-"
    ua = _truncate_ua(request.headers.get("user-agent"))
    audit_log.info(
        "operator_fetch tool_id=%s source=%s requester_ip=%s ua=%s",
        tool.id,
        raw_pointer,
        requester_ip,
        ua,
    )

    return CredentialsOut(
        tool_id=tool.id,
        source=raw_pointer,
        fields=fields,
        retrieved_at=retrieved_at,
    )


@router.get(
    "/health",
    response_model=dict[str, HealthStatus],
    summary="Aggregate cached health for all tools",
)
async def all_health(request: Request) -> dict[str, HealthStatus]:
    """Return `{tool_id: HealthStatus}` from the Redis cache.

    Cold start (before the first background probe) returns an empty dict —
    clients should render 'unknown' until the cache fills.
    """
    registry = _registry()
    cache = _health_cache(request)
    return await _load_health_map(cache, registry.tools)


@router.get(
    "/health/{tool_id}",
    response_model=HealthStatus,
    summary="Force a live re-probe for a single tool (bypasses cache)",
)
async def force_probe(tool_id: str, request: Request) -> HealthStatus:
    registry = _registry()
    tool = get_tool_by_id(registry, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool '{tool_id}' not found")

    client = _http_client(request)
    status = await probe_tool(
        tool, client, timeout_seconds=settings.health_probe_timeout_seconds
    )

    # Write back to cache so subsequent reads see the fresh value immediately.
    cache = _health_cache(request)
    await cache.set_json(
        f"portal:health:{tool_id}",
        status.model_dump(mode="json"),
        ttl_seconds=settings.health_cache_ttl_seconds,
    )
    return status


@router.get(
    "/categories",
    response_model=list[CategoryOut],
    summary="List categories with per-category counts and healthy %",
)
async def list_categories(request: Request) -> list[CategoryOut]:
    registry = _registry()
    cache = _health_cache(request)
    health_map = await _load_health_map(cache, registry.tools)

    by_cat_total: dict[str, int] = {}
    by_cat_healthy: dict[str, int] = {}
    for t in registry.tools:
        by_cat_total[t.category] = by_cat_total.get(t.category, 0) + 1
        hs = health_map.get(t.id)
        if hs and hs.status == "healthy":
            by_cat_healthy[t.category] = by_cat_healthy.get(t.category, 0) + 1

    # Categories referenced by a tool but missing from the `categories:` list
    # are synthesized with neutral metadata after the first pass.
    out: list[CategoryOut] = []
    seen: set[str] = set()
    for c in registry.categories:
        total = by_cat_total.get(c.id, 0)
        healthy = by_cat_healthy.get(c.id, 0)
        out.append(
            CategoryOut(
                id=c.id,
                name=c.name,
                order=c.order,
                color=c.color,
                tool_count=total,
                healthy_count=healthy,
                healthy_pct=round(100.0 * healthy / total, 1) if total else 0.0,
            )
        )
        seen.add(c.id)

    # Categories referenced by a tool but missing from the `categories:` list
    for cat_id, total in by_cat_total.items():
        if cat_id in seen:
            continue
        healthy = by_cat_healthy.get(cat_id, 0)
        out.append(
            CategoryOut(
                id=cat_id,
                name=cat_id.title(),
                order=999,
                color=None,
                tool_count=total,
                healthy_count=healthy,
                healthy_pct=round(100.0 * healthy / total, 1) if total else 0.0,
            )
        )

    out.sort(key=lambda c: (c.order, c.id))
    return out


# ---------------------------------------------------------------------------
# Launch — pick the right URL flavour for the request's origin.
# ---------------------------------------------------------------------------
# Public funnel domain suffix that, when it appears in the Host header, tells
# us the request arrived via the internet-facing Tailscale Funnel + nginx
# wildcard SNI router. In that scenario the user's browser can *only* reach
# tools via public DNS (they don't have the tailnet running), so we MUST
# redirect to `url_funnel` rather than `url_external` (localhost).
#
# Kept as a module constant so tests can monkeypatch it if the domain ever
# changes, and so the value is discoverable via imports.
PUBLIC_FUNNEL_HOST_SUFFIX = ".deepaksharma.live"
PUBLIC_FUNNEL_HOST_APEX = "deepaksharma.live"


def _is_public_host(host: str) -> bool:
    """True if the Host header indicates a public-funnel-served request.

    Matches:
        deepaksharma.live
        deepaksharma.live:443
        grafana.deepaksharma.live
        grafana.deepaksharma.live:443
    Does NOT match:
        deepak-desktop.tailac51e7.ts.net (tailnet — use url_tailnet if you want)
        localhost
        devops-tools-backend (in-cluster)
    """
    if not host:
        return False
    # Strip trailing :port before matching.
    bare = host.split(":", 1)[0]
    return bare == PUBLIC_FUNNEL_HOST_APEX or bare.endswith(PUBLIC_FUNNEL_HOST_SUFFIX)


@router.post(
    "/launch/{tool_id}",
    response_model=LaunchResponse,
    summary="Prepare a redirect URL for launching a tool",
)
async def launch(tool_id: str, request: Request) -> LaunchResponse:
    """Return the URL the browser should navigate to.

    Priority order (first non-empty wins):

        request Host is `*.deepaksharma.live` -> url_funnel (if set)
        in-cluster same-origin heuristic      -> url_internal
        everything else                       -> url_external

    The public-host check is first because a user reaching the portal at
    `https://deepaksharma.live` and clicking "Launch Grafana" must land on
    `https://grafana.deepaksharma.live`, NOT `http://localhost:3000` which is
    meaningless from the public edge.
    """
    registry = _registry()
    tool = get_tool_by_id(registry, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool '{tool_id}' not found")

    host = (request.headers.get("host") or "").lower()

    # --- Public-funnel Host header + tool has a funnel URL? --------------
    # This path runs AFTER the nginx-proxy wildcard SNI router terminates TLS,
    # so Host here is whatever the nginx server_name matched (e.g. the portal
    # apex or api.deepaksharma.live), NOT the per-tool subdomain.
    if _is_public_host(host) and tool.url_funnel:
        redirect = tool.url_funnel
    else:
        # Treat "*.svc", "*.local", bare container hostnames, or any compose
        # hostname as same-origin -> prefer internal URL. Otherwise use
        # external.
        prefer_internal = any(
            host.endswith(suffix) for suffix in (".svc", ".local", ".internal")
        ) or "devops-tools-backend" in host

        redirect = (
            tool.url_internal
            if (prefer_internal and tool.url_internal)
            else tool.url_external
        )
        if not redirect:
            redirect = tool.url_internal or tool.url_external or ""

    if not redirect:
        raise HTTPException(
            status_code=409,
            detail=f"tool '{tool_id}' has no launch URL configured",
        )

    requires_auth = tool.credentials and tool.credentials.lower() != "none"
    return LaunchResponse(
        redirect_url=redirect,
        requires_auth=bool(requires_auth),
        tool_id=tool.id,
    )


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Dashboard KPIs — aggregate + per-category counts",
)
async def stats(request: Request) -> StatsResponse:
    registry = _registry()
    cache = _health_cache(request)
    health_map = await _load_health_map(cache, registry.tools)

    counters = {"healthy": 0, "degraded": 0, "down": 0, "unknown": 0}
    by_category: dict[str, dict[str, int]] = {}

    for t in registry.tools:
        hs = health_map.get(t.id)
        bucket = hs.status if hs else "unknown"
        counters[bucket] = counters.get(bucket, 0) + 1
        cat = by_category.setdefault(
            t.category,
            {"total": 0, "healthy": 0, "degraded": 0, "down": 0, "unknown": 0},
        )
        cat["total"] += 1
        cat[bucket] = cat.get(bucket, 0) + 1

    return StatsResponse(
        total=len(registry.tools),
        healthy=counters["healthy"],
        degraded=counters["degraded"],
        down=counters["down"],
        unknown=counters["unknown"],
        by_category=by_category,
        generated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/tailscale/status",
    response_model=TailscaleStatus,
    summary="Tailscale tailnet status (best-effort, never raises)",
)
async def tailscale_status() -> TailscaleStatus:
    """Try `tailscale status --json`. If unavailable, report local mode."""
    cli = settings.tailscale_cli_path or shutil.which("tailscale")
    if not cli:
        return TailscaleStatus(state="local", error="tailscale CLI not on PATH")

    try:
        proc = await asyncio.create_subprocess_exec(
            cli,
            "status",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return TailscaleStatus(state="local", error="tailscale status timed out")
    except FileNotFoundError:
        return TailscaleStatus(state="local", error="tailscale CLI not found")
    except Exception as exc:  # noqa: BLE001
        log.debug("tailscale subprocess err", exc_info=exc)
        return TailscaleStatus(state="local", error=f"subprocess error: {exc}"[:200])

    if proc.returncode != 0:
        return TailscaleStatus(
            state="local",
            error=f"tailscale exit {proc.returncode}: {stderr.decode(errors='replace')[:200]}",
        )

    try:
        data: dict[str, Any] = json.loads(stdout.decode())
    except json.JSONDecodeError as exc:
        return TailscaleStatus(state="local", error=f"bad JSON: {exc}")

    backend_state = data.get("BackendState", "")
    self_node = data.get("Self") or {}
    hostname = self_node.get("HostName") or self_node.get("DNSName")
    funnel_enabled = False

    # Inspect ServeConfig for funnel toggles, when present.
    serve_config = data.get("ServeConfig") or {}
    if isinstance(serve_config, dict):
        allow = serve_config.get("AllowFunnel") or {}
        funnel_enabled = any(bool(v) for v in allow.values()) if isinstance(allow, dict) else False

    magic_dns: str | None = None
    dns = self_node.get("DNSName")
    if dns:
        magic_dns = dns.rstrip(".")

    if backend_state == "Running":
        return TailscaleStatus(
            state="live",
            hostname=hostname,
            funnel_enabled=funnel_enabled,
            magic_dns=magic_dns,
        )
    if backend_state in {"NeedsLogin", "NoState", "Stopped"}:
        return TailscaleStatus(
            state="down",
            hostname=hostname,
            funnel_enabled=funnel_enabled,
            magic_dns=magic_dns,
            error=f"BackendState={backend_state}",
        )
    return TailscaleStatus(
        state="local",
        hostname=hostname,
        funnel_enabled=funnel_enabled,
        magic_dns=magic_dns,
        error=f"BackendState={backend_state}" if backend_state else None,
    )


# ---------------------------------------------------------------------------
# Background probe loop (started from main.py lifespan)
# ---------------------------------------------------------------------------


async def background_probe_loop(
    cache: HealthCache,
    client: httpx.AsyncClient,
) -> None:
    """Run probe_all on a fixed interval; write results to Redis.

    Catches every exception per-iteration so a transient failure (e.g. a
    registry reload with a typo) doesn't kill the loop.
    """
    interval = settings.health_probe_interval_seconds
    ttl = settings.health_cache_ttl_seconds
    timeout = settings.health_probe_timeout_seconds
    log.info(
        "Portal health probe loop starting (interval=%ss, ttl=%ss, timeout=%ss)",
        interval,
        ttl,
        timeout,
    )

    try:
        while True:
            try:
                registry = _registry()
                results = await probe_all(
                    registry.tools,
                    client,
                    timeout_seconds=timeout,
                    max_concurrent=10,
                )
                # Per-tool keys
                for tool_id, status in results.items():
                    await cache.set_json(
                        f"portal:health:{tool_id}",
                        status.model_dump(mode="json"),
                        ttl_seconds=ttl,
                    )
                # Snapshot blob
                await cache.set_json(
                    "portal:health:all",
                    {tid: s.model_dump(mode="json") for tid, s in results.items()},
                    ttl_seconds=ttl,
                )
                log.debug("portal probe iteration ok (n=%d)", len(results))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("portal probe iteration failed", exc_info=exc)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("Portal health probe loop cancelled")
        raise
