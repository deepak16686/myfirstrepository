# AI Agent Coding Guidelines for Legacy Modernization Platform

## Architecture Overview

This is a **multi-project workspace** for a legacy application modernization platform with three main components:

1. **Java Pipeline** (`java-pipeline/`): Maven-based Java app with GitLab CI/CD, builds to Docker on Nexus registry
2. **FastAPI Service** (`legacy-modernization-api/`): REST API orchestrating legacy code analysis and modernization recommendations
3. **Testing Framework** (`test/`): Pytest-based integration tests with coverage reporting

**Data Flow**: FastAPI exposes `/api/v1/analysis` endpoints → coordinates with backend services (PostgreSQL, Redis, Ollama, ChromaDB, MinIO) → Java pipeline generates artifacts → Docker images pushed to Nexus registry.

## Workspace Structure Conventions

- **Root powershell scripts** (`setup-fastapi.ps1`, `files/rebuild-platform.ps1`): Infrastructure provisioning
- **Configuration files** (`files/docker-compose.yml`, `monitoring-stack.yml`, `security-tools.yml`): Docker stack definitions
- **Desktop content** (`desktop-content/`): Replicated configs for local development
- **Each app folder** is independently deployable with its own `Dockerfile` and `docker-compose.yml`

## Key Files to Reference

- [legacy-modernization-api/app/config.py](legacy-modernization-api/app/config.py): Environment settings for Postgres, Redis, Ollama, MinIO, ChromaDB
- [legacy-modernization-api/app/main.py](legacy-modernization-api/app/main.py): FastAPI app setup with CORS, router includes
- [legacy-modernization-api/app/routers/health.py](legacy-modernization-api/app/routers/health.py): Health/readiness/liveness probes for K8s
- [java-pipeline/pom.xml](java-pipeline/pom.xml): Maven build config, SonarQube plugin enabled
- [java-pipeline/.gitlab-ci.yml](java-pipeline/.gitlab-ci.yml): Docker build + push to Nexus (port 5001) with DinD

## Development Workflows

### FastAPI Development
```powershell
cd legacy-modernization-api
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Swagger UI: http://localhost:8000/docs
```

### Java Pipeline Build & Test
```bash
cd java-pipeline
mvn clean package              # Compiles, runs tests, creates JAR
mvn sonar:sonar               # SonarQube analysis
docker build -t java-app:latest .
```

### Run Full Platform (Docker)
```powershell
cd files
docker-compose up -d          # All services: Postgres, Redis, MinIO, ChromaDB, Ollama, monitoring
docker-compose logs -f        # Stream logs
./validate-platform.ps1       # Health checks
```

### Testing
- **Unit/Integration Tests**: `test/` folder uses pytest with markers (`@pytest.mark.unit`, `integration`, `slow`, `gpu`)
- **Coverage**: Auto-generated in `htmlcov/` and XML reports
- Run tests: `pytest --cov=app` (respects pytest.ini config)

## Pattern Conventions

### FastAPI Routers & Request/Response Handling
- **Location**: `app/routers/` with APIRouter per endpoint group (e.g., `health.py`, `analysis.py`)
- **Pattern**: `@router.get("/path")` or `@router.post("/path")` with type hints, status_code, and docstrings
- **Request/Response Models**: Use `pydantic.BaseModel` for validation (e.g., `AnalysisRequest`, `AnalysisResponse`)
- **Response Fields**: Always include `job_id`, `status`, `created_at`, and `message` for job-tracking endpoints
- **Status Values**: Use lowercase strings (`"initiated"`, `"running"`, `"completed"`, `"failed"`)
- **Health checks**: Three probes—`/health` (general), `/health/ready` (readiness), `/health/live` (liveness)
- **CORS**: Configured with wildcard for dev; restrict in production
- **Background Tasks**: Use FastAPI `BackgroundTasks` for async processing (see `analysis.py` POST pattern)

### Configuration Management
- **Pattern**: Use `pydantic_settings.BaseSettings` with `.env` file (stored in repo, not committed in production)
- **Service URLs**: Injected as env vars with container names as hostnames (e.g., `OLLAMA_URL=http://ollama:11434`)
- **Access via**: `from app.config import settings` then `settings.DATABASE_URL`
- **Defaults**: Always provide sensible defaults for optional settings

### Docker Deployment
- **FastAPI Base**: `python:3.11-slim` with non-root user (UID 1000) for security
- **Java Base**: `amazoncorretto:17-alpine-jdk` for smaller footprint
- **Image naming**: `{NEXUS_REGISTRY}/{IMAGE_NAME}:{IMAGE_TAG}` where `NEXUS_REGISTRY=ai-nexus:5001` (not 5000)
- **DinD setup**: Requires `DOCKER_TLS_CERTDIR=""` and `DOCKER_HOST=tcp://docker:2375` with `--tls=false`
- **Multi-stage builds**: Not currently used; simple FROM → COPY → EXPOSE pattern
- **Caching**: Copy `requirements.txt`/`pom.xml` before source code for layer reuse
- **Health checks**: Include in Dockerfile with CMD-SHELL or curl patterns

### Maven Build Patterns (Java Pipeline)
- **Build command**: `mvn clean package` (compiles, runs unit tests, creates JAR in `target/`)
- **SonarQube**: `mvn sonar:sonar` for code quality analysis (plugin configured in pom.xml)
- **Dependencies**: Use property-based versioning for easy updates (e.g., `${junit.version}`)
- **JAR artifact**: Pushed to GitLab artifacts with 1-hour expiration, reused by Docker build stage

### Database & Persistence
- **PostgreSQL**: User `modernization`, password `modernization123`, default DB `legacy_modernization`
- **Redis**: No auth, used for caching; `redis://redis:6379/0`
- **MinIO**: User/pass `minioadmin`/`minioadmin123`, S3-compatible object storage
- **ChromaDB**: Vector DB for embeddings, HTTP endpoint at port 8000
- **Ollama**: Local LLM inference, port 11434 (models: deepseek-coder:33b, qwen2.5-coder:32b)

### Monitoring & Observability
- **Prometheus**: Metrics collection, port 9090
- **Grafana**: Dashboard UI, port 3000 (admin/admin123)
- **Loki**: Log aggregation with Promtail
- **Jaeger**: Distributed tracing, port 16686
- All stack configs in `files/monitoring-stack.yml`

## Common Gotchas & Tips

1. **Dockerfile base for Java**: Uses Amazon Corretto Alpine 17 (`amazoncorretto:17-alpine-jdk`)—prefer Alpine for smaller images
2. **PowerShell path issues**: Always use absolute paths in scripts; watch for WSL2 path translation (`C:` vs `/mnt/c`)
3. **DinD TLS**: GitLab CI with Docker requires explicit TLS disabled (`--tls=false`) for reliability
4. **Service connectivity**: All services share `modernization-network` bridge; use container names as hostnames (not localhost)
5. **K8s readiness probes**: TODO in [health.py](legacy-modernization-api/app/routers/health.py)—add actual DB/Redis connectivity checks
6. **Environment isolation**: `desktop-content/` mirrors root `files/` for local dev; keep in sync when updating configs
7. **Job tracking pattern**: Analysis endpoints use UUID-based `job_id` with lowercase status strings; important for client-side polling
8. **Config defaults**: FastAPI config has sensible defaults but requires `.env` for non-containerized local runs

## When Adding Features

- **New API endpoints**: Create router in `app/routers/`, include in `main.py`, add health checks if it calls external services
- **New service dependencies**: Add to [config.py](legacy-modernization-api/app/config.py), `docker-compose.yml`, `requirements.txt` (FastAPI) or `pom.xml` (Java)
- **New Docker images**: Update `docker-compose.yml`, sync to `desktop-content/files/`, add to rebuild script
- **CI/CD changes**: Update `.gitlab-ci.yml` carefully—test DinD mount and registry auth before pushing
