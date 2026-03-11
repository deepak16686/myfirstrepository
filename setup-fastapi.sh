#!/usr/bin/env bash
# =============================================================================
# setup-fastapi.sh
# Scaffolds a production-ready FastAPI microservice project.
#
# Usage:
#   ./setup-fastapi.sh [--name <project-name>] [--dir <output-dir>]
# =============================================================================
set -euo pipefail

PROJECT_NAME="${1:-legacy-modernization-api}"
BASE_DIR="${2:-${PROJECT_NAME}}"

# Parse named args too
while (($# > 0)); do
  case "$1" in
    --name|-n) PROJECT_NAME="${2:-}"; BASE_DIR="${PROJECT_NAME}"; shift ;;
    --dir|-d)  BASE_DIR="${2:-}"; shift ;;
    -h|--help)
      cat <<'EOF'
Usage:
  ./setup-fastapi.sh [--name <project-name>] [--dir <output-dir>]

Scaffolds a FastAPI microservice with:
  - Health endpoints (/health, /health/ready, /health/live)
  - PostgreSQL + Redis integration
  - Prometheus metrics
  - Docker + docker-compose
  - Structured logging
EOF
      exit 0 ;;
    *) ;;
  esac
  shift 2>/dev/null || shift
done

log() { printf '[INFO] %s\n' "$*"; }

log "Creating FastAPI project: ${PROJECT_NAME} in ./${BASE_DIR}"

# ── Directory structure ────────────────────────────────────────────────────────
for d in \
  "${BASE_DIR}/app/models" \
  "${BASE_DIR}/app/routers" \
  "${BASE_DIR}/app/services"; do
  mkdir -p "${d}"
  log "Created directory: ${d}"
done

# ── __init__.py files ─────────────────────────────────────────────────────────
for f in \
  "${BASE_DIR}/app/__init__.py" \
  "${BASE_DIR}/app/models/__init__.py" \
  "${BASE_DIR}/app/routers/__init__.py" \
  "${BASE_DIR}/app/services/__init__.py"; do
  touch "${f}"
  log "Created: ${f}"
done

# ── requirements.txt ─────────────────────────────────────────────────────────
cat > "${BASE_DIR}/requirements.txt" <<'EOF'
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
redis==5.0.1
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.26.0
prometheus-client==0.19.0
structlog==24.1.0
EOF
log "Created: requirements.txt"

# ── .env.example ─────────────────────────────────────────────────────────────
cat > "${BASE_DIR}/.env.example" <<EOF
# Database
DATABASE_URL=postgresql://postgres:postgres@ai-postgres:5432/${PROJECT_NAME}

# Redis
REDIS_URL=redis://redis:6379/0

# Service
SERVICE_NAME=${PROJECT_NAME}
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8080
LOG_LEVEL=INFO

# Secrets (use Vault in production)
SECRET_KEY=change-me-in-production
EOF
log "Created: .env.example"

# ── app/config.py ─────────────────────────────────────────────────────────────
cat > "${BASE_DIR}/app/config.py" <<EOF
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    service_name: str = "${PROJECT_NAME}"
    service_host: str = "0.0.0.0"
    service_port: int = 8080
    log_level: str = "INFO"

    database_url: str = "postgresql://postgres:postgres@ai-postgres:5432/${PROJECT_NAME}"
    redis_url: str = "redis://redis:6379/0"
    secret_key: str = "change-me-in-production"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
EOF
log "Created: app/config.py"

# ── app/main.py ───────────────────────────────────────────────────────────────
cat > "${BASE_DIR}/app/main.py" <<EOF
import time
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from app.config import get_settings
from app.routers import health, analysis

settings = get_settings()
log = structlog.get_logger()

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", service=settings.service_name)
    yield
    log.info("shutdown", service=settings.service_name)


app = FastAPI(
    title=settings.service_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(health.router, tags=["health"])
app.include_router(analysis.router, prefix="/analysis", tags=["analysis"])


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/info")
def info():
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "ok",
    }
EOF
log "Created: app/main.py"

# ── app/routers/health.py ─────────────────────────────────────────────────────
cat > "${BASE_DIR}/app/routers/health.py" <<'EOF'
import time
import psutil
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()
START_TIME = time.time()


@router.get("/health")
def health():
    return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME)}


@router.get("/health/ready")
def readiness():
    """Readiness: dependencies must be reachable."""
    checks = {}
    ok = True

    # PostgreSQL
    try:
        from sqlalchemy import create_engine, text
        from app.config import get_settings
        engine = create_engine(get_settings().database_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
        ok = False

    # Redis
    try:
        import redis as redis_lib
        from app.config import get_settings
        r = redis_lib.from_url(get_settings().redis_url, socket_connect_timeout=3)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        ok = False

    status_code = 200 if ok else 503
    return JSONResponse(content={"status": "ready" if ok else "not ready", "checks": checks},
                        status_code=status_code)


@router.get("/health/live")
def liveness():
    """Liveness: process is alive."""
    mem = psutil.virtual_memory()
    return {
        "status": "ok",
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": mem.percent,
        "uptime_seconds": int(time.time() - START_TIME),
    }
EOF
log "Created: app/routers/health.py"

# ── app/routers/analysis.py ───────────────────────────────────────────────────
cat > "${BASE_DIR}/app/routers/analysis.py" <<'EOF'
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# In-memory store (replace with Redis/DB in production)
_jobs: dict[str, dict] = {}


class AnalysisRequest(BaseModel):
    name: str
    description: Optional[str] = None


class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    name: str


@router.post("", response_model=AnalysisResponse, status_code=202)
def start_analysis(req: AnalysisRequest):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"job_id": job_id, "status": "pending", "name": req.name}
    return _jobs[job_id]


@router.get("/{job_id}", response_model=AnalysisResponse)
def get_analysis(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=list[AnalysisResponse])
def list_analyses():
    return list(_jobs.values())
EOF
log "Created: app/routers/analysis.py"

# ── Dockerfile ────────────────────────────────────────────────────────────────
cat > "${BASE_DIR}/Dockerfile" <<EOF
# Stage 1: build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime
FROM python:3.12-slim
RUN useradd -m -r appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \\
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
EOF
log "Created: Dockerfile"

# ── .dockerignore ────────────────────────────────────────────────────────────
cat > "${BASE_DIR}/.dockerignore" <<'EOF'
__pycache__/
*.pyc
*.pyo
.env
.git
.gitignore
*.md
tests/
.pytest_cache/
EOF
log "Created: .dockerignore"

# ── docker-compose.yml ────────────────────────────────────────────────────────
cat > "${BASE_DIR}/docker-compose.yml" <<EOF
# App-stack compose — connects to shared infra-stack via external network.
# Start infra-stack first:  cd ../infra-stack && ./scripts/infra.sh up core
services:
  ${PROJECT_NAME}:
    build: .
    container_name: ${PROJECT_NAME}
    restart: unless-stopped
    ports:
      - "8080:8080"
    env_file:
      - .env
    networks:
      - global-infra-net
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8080/health || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  global-infra-net:
    external: true
EOF
log "Created: docker-compose.yml"

# ── .gitignore ────────────────────────────────────────────────────────────────
cat > "${BASE_DIR}/.gitignore" <<'EOF'
__pycache__/
*.pyc
*.pyo
.env
*.egg-info/
dist/
build/
.venv/
EOF
log "Created: .gitignore"

# ── Make scripts executable ───────────────────────────────────────────────────
printf '\n'
log "Project scaffolded at: ./${BASE_DIR}"
log ""
log "Quick start:"
printf '  cd %s\n' "${BASE_DIR}"
printf '  cp .env.example .env\n'
printf '  # Edit .env with real credentials\n'
printf '  docker compose up -d --build\n'
printf '\n'
log "Requires infra-stack core services (postgres, redis) to be running."
