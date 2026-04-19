"""
DevOps Tools Backend - Unified API for DevOps tool integrations

This backend provides a unified API layer for integrating with various DevOps tools:
- GitLab: CI/CD, repositories, pipelines
- SonarQube: Code quality, security analysis
- Trivy: Container security scanning
- Nexus: Artifact repository management
- Ollama: LLM integration
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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings, tools_manager
from app.integrations.redis_client import HealthCache
from app.integrations.vault import VaultClient, build_vault_client
from app.routers import (
    chat,
    gitlab,
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
# Root endpoints
# ============================================================================

@app.get("/")
async def root():
    """Serve frontend UI"""
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health"
    }


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
app.include_router(portal_router.router, prefix=settings.api_prefix)
app.include_router(chat.router)  # Chat API has its own prefix

# ============================================================================
# Static files for frontend
# ============================================================================

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    # Also serve CSS and JS directly
    @app.get("/styles.css")
    async def get_styles():
        return FileResponse(os.path.join(frontend_dir, "styles.css"), media_type="text/css")

    @app.get("/app.js")
    async def get_app_js():
        return FileResponse(os.path.join(frontend_dir, "app.js"), media_type="application/javascript")


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
