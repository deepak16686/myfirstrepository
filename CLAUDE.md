# CLAUDE.md — AI Assistant Guide for Legacy Modernization Platform

## Project Overview

This is an **AI-driven legacy application modernization platform** that analyzes legacy codebases and generates modernized artifacts (Dockerfiles, CI/CD pipelines). It consists of three core components plus supporting DevOps tooling.

## Repository Structure

```
/
├── legacy-modernization-api/    # FastAPI REST service — orchestrates analysis workflows
│   ├── app/
│   │   ├── main.py              # App entrypoint with CORS & router registration
│   │   ├── config.py            # Pydantic settings (DB, Redis, Ollama, MinIO, ChromaDB)
│   │   ├── routers/
│   │   │   ├── health.py        # Health/readiness/liveness probes
│   │   │   └── analysis.py      # Analysis job creation & status tracking
│   │   ├── models/              # Pydantic request/response models
│   │   └── services/            # Business logic layer
│   ├── Dockerfile               # Python 3.11-slim, non-root UID 1000
│   ├── docker-compose.yml       # Local dev stack (FastAPI + Postgres + Redis + Ollama + MinIO + ChromaDB)
│   └── requirements.txt         # FastAPI, Pydantic, SQLAlchemy, httpx, etc.
│
├── rag-ai/                      # RAG-based Dockerfile & GitLab CI generator
│   ├── generator_api.py         # FastAPI service with ChromaDB retrieval
│   ├── ingest_templates.py      # Populates ChromaDB with templates
│   ├── create_collections.py    # ChromaDB collection setup
│   ├── catalog_refresh.py       # Docker image catalog updater
│   ├── catalog.json             # Nexus registry image catalog
│   ├── rag_corpus/
│   │   ├── dockerfiles/         # Template Dockerfiles (Python, Node, Java) with metadata
│   │   ├── gitlab/              # Template CI pipelines (Python, Node, Java) with metadata
│   │   └── rag_specs/
│   │       └── golden_rules.md  # Non-negotiable generation constraints
│   ├── test_generator.py        # Integration tests for generator API
│   ├── test_retrieval.py        # ChromaDB retrieval tests
│   └── requirements.txt         # FastAPI, ChromaDB, requests, pyyaml
│
├── plane/                       # Redmine/Plane project management automation
│   ├── setup_redmine.rb         # Redmine initialization
│   ├── configure_project.rb     # Project configuration
│   ├── create_trackers.rb       # Issue tracker template creation
│   ├── full_setup.rb            # Complete setup orchestrator
│   └── docker-compose.yml       # Redmine + PostgreSQL
│
├── gitlab-runner/               # GitLab CI runner configuration
│   └── config/                  # Runner docker-compose & config.toml
│
├── monitoring/
│   └── prometheus.yml           # Prometheus scrape configuration
│
├── nexus/                       # Nexus registry helper scripts (Bash)
│   ├── push-images-to-nexus.sh
│   ├── push-language-stacks-to-nexus.sh
│   └── push-to-apm-repo-demo.sh
│
├── *.py                         # ~55 root-level Python scripts (OpenWebUI tools, utilities, tests)
├── monitoring-stack.yml         # Full observability stack (Prometheus, Grafana, Loki, Jaeger, cAdvisor)
├── security-tools.yml           # Security stack (Trivy, Loki, Jaeger)
├── .github/
│   └── copilot-instructions.md  # Existing AI coding guidelines
└── .gitignore
```

## Languages and Technologies

| Language/Tool | Usage |
|---|---|
| **Python** | Primary language (~55 files). FastAPI services, OpenWebUI tools, utilities, tests |
| **Ruby** | Redmine/Plane automation scripts (6 files in `plane/`) |
| **Bash/PowerShell** | Infrastructure provisioning and registry scripts |
| **Docker/Compose** | All services containerized; multiple compose files for different stacks |
| **GitLab CI** | CI/CD pipelines with DinD (Docker-in-Docker) via Kaniko builder |
| **YAML/JSON** | Configuration, pipeline templates, metadata |

## Build and Run Commands

### FastAPI Service (legacy-modernization-api)
```bash
cd legacy-modernization-api
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Swagger UI: http://localhost:8000/docs
```

### RAG Generator (rag-ai)
```bash
cd rag-ai
pip install -r requirements.txt
uvicorn generator_api:app --reload --host 0.0.0.0 --port 8001
```

### Full Docker Platform
```bash
cd legacy-modernization-api
docker-compose up -d    # Starts all backend services
docker-compose logs -f  # Stream logs
```

## Testing

### Test Framework
Tests are custom Python scripts (not pytest-based). All existing tests are **integration tests** requiring live infrastructure.

### Running Tests

**RAG AI tests** (require running ChromaDB + generator API):
```bash
cd rag-ai
python test_generator.py
python test_retrieval.py
```

**RAG AI tests via PowerShell runner:**
```powershell
cd rag-ai
./run_tests.ps1
```

**Root-level integration tests** (require OpenWebUI, SonarQube, GitLab, Nexus, Redmine):
```bash
python test_project_validator.py
python test_pipeline_tool.py
python test_nexus_tool.py
```

### Test Coverage Gaps
There are **no unit tests**. All tests require live services. See `TEST_COVERAGE_ANALYSIS.md` for a detailed gap analysis. Key untested areas:
- `legacy-modernization-api/` has zero test coverage
- No mocked/isolated tests for any component
- No pytest integration or coverage reporting

## Key Architecture Patterns

### FastAPI Conventions
- **Routers**: One file per feature in `app/routers/`, registered in `main.py`
- **Models**: Pydantic `BaseModel` for all request/response schemas
- **Config**: `pydantic_settings.BaseSettings` in `config.py`, loaded from `.env`
- **Job tracking**: UUID-based `job_id` with lowercase status strings: `"initiated"`, `"running"`, `"completed"`, `"failed"`
- **Required response fields**: `job_id`, `status`, `created_at`, `message`
- **Health probes**: `/health` (general), `/health/ready` (readiness), `/health/live` (liveness)
- **Background tasks**: FastAPI `BackgroundTasks` for async processing

### RAG Generator Conventions
- ChromaDB stores templates in separate collections (dockerfiles, gitlab-ci, golden-rules)
- Template retrieval via vector similarity, then placeholder substitution (`${BASE_REGISTRY}`, etc.)
- All generated artifacts validated against golden rules before returning
- Supports Java (Maven/Corretto 17), Python (3.12-slim), Node.js (Alpine)

### Docker and Registry Rules
- **ALL base images must come from the private Nexus registry** (`ai-nexus:5001`) — public registries (docker.io, ghcr.io) are forbidden
- Image naming: `${NEXUS_REGISTRY}/apm-repo/demo/<image>:<tag>`
- Non-root containers: UID 1000 user required
- Layer caching: copy dependency files (requirements.txt, pom.xml) before source code
- Health checks: `HEALTHCHECK` with 30s interval, 10s timeout, 3 retries

### GitLab CI Pipeline Conventions
- Required stages: `compile` -> `build` -> `test` -> `sast` -> `quality` -> `security` -> `docker_build` -> `docker_scan` -> `docker_push` -> `notify`
- DinD setup: `DOCKER_TLS_CERTDIR=""`, `DOCKER_HOST=tcp://docker:2375`, `--tls=false`
- Kaniko for Docker builds (no Docker daemon required)
- Artifact expiration: 1 hour for build artifacts
- Registry auth via JSON config at `/kaniko/.docker/config.json`

### OpenWebUI Tool Pattern
Root-level Python scripts follow a consistent pattern for deploying tools to OpenWebUI:
- Functions wrapped as OpenWebUI tools via `open_webui.models.tools`
- Embedded function definitions as multiline strings using `textwrap.dedent`
- All credentials and endpoints from environment variables
- Structured error responses with actionable escalation (Jira/Redmine/Slack)

## Service Dependencies and Networking

All services communicate over a shared Docker bridge network using container names as hostnames:

| Service | Default URL | Purpose |
|---|---|---|
| PostgreSQL | `postgresql://postgres:postgres@postgres:5432/modernization` | Primary database |
| Redis | `redis://redis:6379/0` | Caching, no auth |
| Ollama | `http://ollama:11434` | Local LLM inference |
| MinIO | `http://minio:9000` (credentials: `minioadmin`/`minioadmin`) | S3-compatible object storage |
| ChromaDB | `http://chromadb:8000` | Vector database for RAG |
| SonarQube | `http://ai-sonarqube:9000` | Code quality analysis |
| Nexus | `ai-nexus:5001` (Docker registry), `:8081` (artifacts) | Private artifact/image registry |
| GitLab | `http://gitlab-server` | Source control and CI/CD |
| Prometheus | `http://prometheus:9090` | Metrics collection |
| Grafana | `http://grafana:3000` (credentials: `admin`/`admin123`) | Dashboards |

## Important Constraints

1. **Never use public container registries** — all images must come from the internal Nexus registry
2. **Never hardcode secrets** in source code; use environment variables or `.env` files
3. **Always validate generated artifacts** — YAML syntax, Dockerfile syntax, no public registry references
4. **Use container names as hostnames** for inter-service communication (not `localhost`)
5. **Maintain non-root security** in all Dockerfiles (UID 1000)
6. **Follow the golden rules** in `rag-ai/rag_corpus/rag_specs/golden_rules.md` for all generation

## Common Gotchas

- **DinD TLS**: GitLab CI with Docker-in-Docker requires explicit TLS disabled (`--tls=false`)
- **Nexus port**: Docker registry is port `5001` (not `5000`)
- **Service connectivity**: Use container names, not `localhost`, inside Docker networks
- **Config defaults**: FastAPI config has Docker-network defaults; local runs need a `.env` file
- **Health probes**: The readiness/liveness checks in `health.py` are stubs — they don't verify actual DB/Redis connectivity yet
- **PowerShell paths**: Watch for WSL2 path translation issues (`C:` vs `/mnt/c`)

## When Adding Features

- **New API endpoint**: Create router in `app/routers/`, register in `main.py`, add health check if it calls external services
- **New service dependency**: Add to `config.py`, `docker-compose.yml`, and `requirements.txt`
- **New Docker image**: Update relevant `docker-compose.yml`, add to Nexus push scripts
- **New CI pipeline template**: Add to `rag-ai/rag_corpus/gitlab/` with matching `.meta.json`, run `ingest_templates.py`
- **New Dockerfile template**: Add to `rag-ai/rag_corpus/dockerfiles/` with matching `.meta.json`, run `ingest_templates.py`
- **CI/CD changes**: Test DinD mount and registry auth locally before pushing
