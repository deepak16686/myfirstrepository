"""
DevOps Tools Backend - Unified API for DevOps tool integrations

This backend provides a unified API layer for integrating with various DevOps tools:
- GitLab: CI/CD, repositories, pipelines
- SonarQube: Code quality, security analysis
- Trivy: Container security scanning
- Nexus: Artifact repository management
- Ollama: LLM integration
- ChromaDB: Vector database for RAG

Features:
- Dynamic tool configuration
- Unified tool calling API for AI integration
- RESTful endpoints for each tool
- Health monitoring and status checks
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.config import settings, tools_manager
from app.routers import tools, gitlab, sonarqube, trivy, nexus, unified, pipeline, chat, github_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Loaded {len(tools_manager.list_tools())} tools")
    yield
    # Shutdown
    print("Shutting down...")


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
app.include_router(github_pipeline.router, prefix=settings.api_prefix)
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
