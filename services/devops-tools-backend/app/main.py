"""
DevOps Tools Backend - Unified API for DevOps tool integrations

This backend provides a unified API layer for integrating with various DevOps tools:
- GitLab: CI/CD, repositories, pipelines
- SonarQube: Code quality, security analysis
- Trivy: Container security scanning
- Nexus: Artifact repository management
- LLM provider: Codex Code by default, with local/legacy alternatives
- ChromaDB: Vector database for RAG
- Portal: Unified catalog + live health for every locally-hosted tool

Features:
- Dynamic tool configuration
- Unified tool calling API for AI integration
- RESTful endpoints for each tool
- Health monitoring and status checks
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings, tools_manager
from app.integrations.redis_client import HealthCache
from app.integrations.vault import VaultClient, build_vault_client
from app.routers import (
    chat,
    github_pipeline,
    gitlab,
    jenkins_pipeline,
    nexus,
    pipeline,
    sonarqube,
    tools,
    trivy,
    unified,
)
from app.routers import portal as portal_router
from app.services.tool_registry import load_registry

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    On startup:
        * validate the tool registry loads (fail fast on missing YAML),
        * connect the Redis-backed health cache (fallback to in-memory),
        * open a shared httpx.AsyncClient for probes,
        * spawn the periodic probe task and stash its handle on app.state.

    On shutdown: cancel the probe task, close the client, close Redis.
    """
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Loaded {len(tools_manager.list_tools())} tools")

    # --- Portal wiring --------------------------------------------------
    try:
        registry = load_registry(settings.tools_registry_path)
        print(f"Portal registry loaded: {len(registry.tools)} tools from {settings.tools_registry_path}")
    except FileNotFoundError as exc:
        # Hard fail — the portal explicitly forbids silent empty-catalog mode.
        raise RuntimeError(
            f"Portal tool registry missing: {exc}. Set TOOLS_REGISTRY_PATH or create config/tools.yaml."
        ) from exc

    cache = HealthCache(
        redis_url=settings.redis_url,
        default_ttl_seconds=settings.health_cache_ttl_seconds,
    )
    await cache.connect()
    app.state.portal_health_cache = cache

    http_client = httpx.AsyncClient(timeout=settings.health_probe_timeout_seconds)
    app.state.portal_http_client = http_client

    # Vault client for the operator credentials endpoint. Returns None when
    # VAULT_ADDR / VAULT_TOKEN are unset — the portal router then answers
    # 503 on /tools/{id}/credentials.
    vault_client: VaultClient | None = build_vault_client(settings)
    app.state.vault_client = vault_client
    if vault_client is not None:
        log.info("Vault client wired for portal credentials endpoint")
    else:
        log.info("Vault client disabled — credentials endpoint will return 503")

    probe_task = asyncio.create_task(
        portal_router.background_probe_loop(cache, http_client),
        name="portal-health-probe",
    )
    app.state.portal_probe_task = probe_task

    try:
        yield
    finally:
        # --- Shutdown ---------------------------------------------------
        print("Shutting down...")
        task: asyncio.Task | None = getattr(app.state, "portal_probe_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
                log.debug("probe task shutdown: %s", exc)

        client: httpx.AsyncClient | None = getattr(app.state, "portal_http_client", None)
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass

        vault_obj: VaultClient | None = getattr(app.state, "vault_client", None)
        if vault_obj is not None:
            try:
                await vault_obj.aclose()
            except Exception:  # noqa: BLE001
                pass

        cache_obj: HealthCache | None = getattr(app.state, "portal_health_cache", None)
        if cache_obj is not None:
            await cache_obj.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=__doc__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Root + SPA serving
# ----------------------------------------------------------------------------
# The portal frontend is a Vite + React SPA built into frontend/dist/. We
# serve it from this FastAPI app so the single backend container handles both
# `/api/*` and `/` + client-side routes (`/tools`, `/pipelines`, `/embed/...`).
#
# Routing contract:
#   /                      -> dist/index.html           (SPA bootstrap)
#   /favicon.svg           -> dist/favicon.svg          (static)
#   /assets/<hash>.{js,css,woff2}  -> dist/assets/...   (mount, long cache)
#   /api/*, /docs, /redoc, /openapi.json -> API routers (registered earlier)
#   /<anything-else>       -> dist/index.html           (SPA fallback for
#                                                        client-side routing)
#
# The SPA fallback MUST be registered LAST so the API routers match first.
# ============================================================================

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
FRONTEND_DIST = os.path.join(FRONTEND_DIR, "dist")
FRONTEND_INDEX = os.path.join(FRONTEND_DIST, "index.html")
FRONTEND_ASSETS = os.path.join(FRONTEND_DIST, "assets")
FRONTEND_FAVICON = os.path.join(FRONTEND_DIST, "favicon.svg")

# Paths that must NEVER fall through to the SPA (return real 404 instead).
# Kept as a tuple for startswith checks; order does not matter.
# NB: do NOT add bare "chat" here — that prefix would swallow the SPA route
# `/chat` (the AI Chat page) and break the React Router. The chat backend
# is already covered by the `api/` prefix (mounted at `/api/v1/chat/`).
_API_PREFIXES = ("api/", "docs", "redoc", "openapi.json", "assets/", "static/")


@app.get("/")
async def root():
    """Serve the SPA shell or a JSON fallback when the bundle is missing."""
    if os.path.isfile(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX, media_type="text/html")
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "note": "frontend/dist/index.html missing — run `npm run build` in frontend/",
    }


@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    if os.path.isfile(FRONTEND_FAVICON):
        return FileResponse(FRONTEND_FAVICON, media_type="image/svg+xml")
    return Response(status_code=404)


@app.get("/api")
async def api_info():
    """API info endpoint"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.app_version}


@app.get("/api/v1/status")
async def api_status():
    """Get status of all configured tools"""
    tools_status = {}
    for name, config in tools_manager.list_tools().items():
        tools_status[name] = {
            "enabled": config.enabled,
            "base_url": config.base_url
        }
    return {
        "api_version": "v1",
        "tools": tools_status
    }


# ============================================================================
# Include routers
# ============================================================================

app.include_router(tools.router, prefix=settings.api_prefix)
app.include_router(gitlab.router, prefix=settings.api_prefix)
app.include_router(sonarqube.router, prefix=settings.api_prefix)
app.include_router(trivy.router, prefix=settings.api_prefix)
app.include_router(nexus.router, prefix=settings.api_prefix)
app.include_router(unified.router, prefix=settings.api_prefix)
app.include_router(pipeline.router, prefix=settings.api_prefix)
# Jenkins + GitHub Actions pipeline generators (restored from pre-cleanup 73aa217).
# Each router declares its own prefix (/jenkins-pipeline, /github-pipeline) so the
# API prefix just puts them under /api/v1/.
app.include_router(jenkins_pipeline.router, prefix=settings.api_prefix)
app.include_router(github_pipeline.router, prefix=settings.api_prefix)
app.include_router(portal_router.router, prefix=settings.api_prefix)
app.include_router(chat.router)  # Chat API has its own prefix

# ============================================================================
# Static files for frontend
# ----------------------------------------------------------------------------
# Mount the Vite build output:
#   * /assets/* -> frontend/dist/assets/*   (hashed, immutable — long cache)
#   * /static/* -> frontend/dist/           (legacy compatibility; optional)
# StaticFiles.html=False so a stray request to /assets/ (no filename) 404s
# instead of trying to auto-serve an index — keeps the SPA fallback in charge.
# ============================================================================

if os.path.isdir(FRONTEND_ASSETS):
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_ASSETS, html=False),
        name="spa-assets",
    )

if os.path.isdir(FRONTEND_DIST):
    app.mount(
        "/static",
        StaticFiles(directory=FRONTEND_DIST, html=False),
        name="spa-static",
    )


# ============================================================================
# SPA fallback — MUST be registered last so every prior route/mount wins.
# Client-side routes (/tools, /pipelines, /embed/<id>, /chat, /...) hit this
# and get the SPA shell back with 200, letting React Router take over.
# ============================================================================

@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str, request: Request):
    # Never absorb API/docs/assets — those should 404 cleanly if missing.
    if full_path.startswith(_API_PREFIXES):
        raise HTTPException(status_code=404, detail="Not Found")
    if os.path.isfile(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX, media_type="text/html")
    raise HTTPException(status_code=404, detail="Frontend bundle missing")


# ============================================================================
# Error handlers
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "detail": str(exc) if settings.debug else None
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
