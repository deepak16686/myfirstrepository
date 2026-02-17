# Legacy Modernization Platform — Complete Application Guide

## Table of Contents

1. [What This Application Does](#1-what-this-application-does)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Component Deep Dive](#3-component-deep-dive)
   - [3.1 FastAPI REST Service](#31-fastapi-rest-service-legacy-modernization-api)
   - [3.2 RAG-Based Generator](#32-rag-based-generator-rag-ai)
   - [3.3 OpenWebUI AI Tools](#33-openwebui-ai-tools-root-level-python-scripts)
   - [3.4 Project Management (Redmine)](#34-project-management--ticketing-plane)
   - [3.5 GitLab CI/CD Runner](#35-gitlab-cicd-runner-gitlab-runner)
   - [3.6 Monitoring & Observability](#36-monitoring--observability)
   - [3.7 Security Tooling](#37-security-tooling)
   - [3.8 Nexus Private Registry](#38-nexus-private-registry-nexus)
4. [End-to-End Data Flow](#4-end-to-end-data-flow)
5. [Infrastructure & Networking](#5-infrastructure--networking)
6. [Nexus Image Catalog](#6-nexus-image-catalog)
7. [Golden Rules — Non-Negotiable Constraints](#7-golden-rules--non-negotiable-constraints)
8. [How to Run Everything](#8-how-to-run-everything)
9. [API Reference](#9-api-reference)
10. [File-by-File Reference](#10-file-by-file-reference)
11. [Current Limitations & TODOs](#11-current-limitations--todos)

---

## 1. What This Application Does

This platform automates the modernization of legacy applications by:

1. **Analyzing legacy codebases** — A user submits a repository URL, and the platform inspects its structure, language, and dependencies.
2. **Generating containerized artifacts** — Using a RAG (Retrieval-Augmented Generation) approach backed by ChromaDB, the system generates Dockerfiles and GitLab CI pipelines tailored to the detected technology stack (Java, Python, Node.js).
3. **Enforcing enterprise standards** — All generated artifacts use only private Nexus registry images (never public Docker Hub), include mandatory security scanning stages, and pass validation gates before being returned.
4. **Deploying to GitLab** — Generated files are committed directly to GitLab repositories and CI/CD pipelines are triggered automatically.
5. **Escalating failures** — When validation detects missing projects in SonarQube, GitLab, or Nexus, the system auto-generates ticketing payloads for Redmine/Jira/ServiceNow with step-by-step remediation guidance.

The platform is designed for an enterprise environment where developers interact with it through **OpenWebUI** (a ChatGPT-like interface) — they ask the AI to "create a pipeline for my Java project" and the system generates, validates, commits, and deploys everything automatically.

---

## 2. High-Level Architecture

```
                                    +-------------------+
                                    |    OpenWebUI       |
                                    |  (Chat Interface)  |
                                    +--------+----------+
                                             |
                              AI model calls tool functions
                                             |
                    +------------------------+------------------------+
                    |                        |                        |
           +-------v--------+     +---------v--------+     +---------v--------+
           | Pipeline        |     | Project           |     | GitLab Commit    |
           | Generator Tool  |     | Validator Tool    |     | & Deploy Tool    |
           +-------+--------+     +---------+--------+     +---------+--------+
                   |                        |                        |
         +---------v----------+    +--------v---------+    +---------v--------+
         | Nexus Registry     |    | SonarQube        |    | GitLab Server    |
         | (Image Catalog)    |    | GitLab           |    | (Commits + CI)   |
         +--------------------+    | Nexus             |    +------------------+
                                   +------------------+
           +------------------+
           | RAG Generator    |     +---------+--------+
           | API (FastAPI)    +---->| ChromaDB          |
           +------------------+     | (Vector DB)       |
                                    +------------------+
           +------------------+
           | Modernization    |     +---------+--------+     +------------------+
           | API (FastAPI)    +---->| PostgreSQL        |     | Redis (Cache)    |
           +------------------+     +------------------+     +------------------+
                                    +------------------+     +------------------+
                                    | Ollama (LLM)     |     | MinIO (Storage)  |
                                    +------------------+     +------------------+

         +--------------------------------------------------------------+
         | Monitoring: Prometheus + Grafana + Loki + Jaeger + cAdvisor  |
         +--------------------------------------------------------------+
         | Security: Trivy (Container Scanning) + SonarQube (SAST)     |
         +--------------------------------------------------------------+
         | Ticketing: Redmine (Escalation tickets for failures)        |
         +--------------------------------------------------------------+
```

---

## 3. Component Deep Dive

### 3.1 FastAPI REST Service (`legacy-modernization-api/`)

**Purpose:** The central orchestration API that receives analysis requests from users, coordinates backend services, and tracks jobs.

**Key files:**

| File | What it does |
|---|---|
| `app/main.py` | Creates the FastAPI app, registers CORS middleware (wildcard for dev), and mounts the `health` and `analysis` routers under `/api/v1` |
| `app/config.py` | Pydantic `BaseSettings` class that loads configuration from environment variables or `.env` file. Defines connection URLs for PostgreSQL, Redis, Ollama, MinIO, and ChromaDB |
| `app/routers/health.py` | Three health endpoints: `/api/v1/health` (returns CPU/memory stats via `psutil`), `/api/v1/health/ready` (Kubernetes readiness probe — stub), `/api/v1/health/live` (liveness probe — stub) |
| `app/routers/analysis.py` | Three analysis endpoints: `POST /api/v1/analysis/start` (creates a UUID-based job), `GET /api/v1/analysis/{job_id}` (checks job status), `GET /api/v1/analysis` (lists all jobs with pagination) |
| `Dockerfile` | Python 3.11-slim base, installs system deps (gcc, libpq), creates non-root user (UID 1000), runs uvicorn with 4 workers |
| `docker-compose.yml` | Runs the FastAPI container on port 8002 (mapped from internal 8000), mounts `app/` for hot reload, connects to external `modernization-network` |
| `requirements.txt` | FastAPI 0.109.0, Pydantic 2.5.3, SQLAlchemy 2.0.25, Redis 5.0.1, httpx 0.26.0, python-jose (JWT), passlib (password hashing), psutil |

**How analysis works:**

```
1. User POSTs to /api/v1/analysis/start with:
   {
     "repository_url": "https://gitlab.example.com/team/legacy-app",
     "branch": "main",
     "analysis_type": "full"   // full | security | performance | architecture
   }

2. Server generates a UUID job_id and returns:
   {
     "job_id": "a1b2c3d4-...",
     "status": "initiated",
     "repository": "https://gitlab.example.com/team/legacy-app",
     "branch": "main",
     "created_at": "2025-01-15T10:30:00",
     "message": "Analysis job created successfully"
   }

3. User polls GET /api/v1/analysis/{job_id} for status updates.
   Status values: "initiated" -> "running" -> "completed" or "failed"
```

> **Note:** The background task processing (`process_analysis`) is still a TODO. The API currently returns stub responses.

---

### 3.2 RAG-Based Generator (`rag-ai/`)

**Purpose:** The core intelligence of the platform. Uses ChromaDB vector search to find the best-matching template for a given technology stack, then fills in placeholders to generate production-ready Dockerfiles and GitLab CI pipelines.

**Key files:**

| File | What it does |
|---|---|
| `generator_api.py` | FastAPI service (port 8080) with 6 endpoints for generating and validating Dockerfiles and CI pipelines |
| `create_collections.py` | Creates three ChromaDB collections: `templates_dockerfile`, `templates_gitlab`, `golden_rules` |
| `ingest_templates.py` | Reads template files from `rag_corpus/` along with their `.meta.json` metadata, and upserts them into ChromaDB |
| `catalog_refresh.py` | Queries the Nexus Docker registry API (`/v2/_catalog`), gets all repositories and tags, selects preferred tags per stack, and writes `catalog.json` |
| `catalog.json` | The current snapshot of all 40+ base images available in the private Nexus registry, with their tags and selected defaults |

**How generation works (Dockerfile example):**

```
1. User calls POST /generate/dockerfile with:
   { "stack": "java", "framework": "spring", "port": 8080, "workdir": "/app" }

2. The API resolves the base image from catalog.json:
   "java" -> localhost:5001/apm-repo/demo/amazoncorretto:17-alpine-jdk

3. It queries ChromaDB for the best matching Dockerfile template:
   dockerfile_collection.query(
     query_texts=["java spring application"],
     n_results=1,
     where={"stack": "java"}
   )

4. The retrieved template (java-v1.dockerfile) looks like:
   ARG BASE_REGISTRY=ai-nexus:5001
   FROM ${BASE_REGISTRY}/apm-repo/demo/amazoncorretto:17-alpine-jdk
   WORKDIR /app
   COPY target/app.jar app.jar
   EXPOSE 8080
   ENTRYPOINT ["java", "-jar", "app.jar"]

5. The API fills placeholders (port, workdir) and validates:
   - Checks for public registry references (docker.io, ghcr.io)
   - If any are found, returns HTTP 400 VALIDATION_FAILED

6. Returns the generated Dockerfile with an audit trail:
   {
     "content": "<the dockerfile>",
     "audit": {
       "template_id": "java-v1",
       "base_image": "localhost:5001/apm-repo/demo/amazoncorretto:17-alpine-jdk",
       "stack": "java",
       "generated_at": "2025-01-15T10:30:00"
     }
   }
```

**Template corpus (`rag_corpus/`):**

Each template has two files — the actual template and a metadata JSON:

| Template | Base Image | Purpose |
|---|---|---|
| `python-v1.dockerfile` | `python:3.12-slim` from Nexus | Python FastAPI app with pip install + uvicorn |
| `java-v1.dockerfile` | `amazoncorretto:17-alpine-jdk` from Nexus | Java app running a JAR file |
| `node-v1.dockerfile` | `node:20-alpine` from Nexus | Node.js app with npm ci + server.js |
| `python-v1.yml` | Various Nexus images per stage | Python CI: test -> build -> security -> quality -> push -> notify |
| `java-v1.yml` | Various Nexus images per stage | Java CI: compile -> build -> test -> sast -> quality -> security -> push -> notify |
| `node-v1.yml` | Various Nexus images per stage | Node.js CI pipeline |

**Metadata format** (e.g., `python-v1.meta.json`):
```json
{
  "template_type": "runtime",
  "stack": "python",
  "tags": ["fastapi", "uvicorn", "pip"],
  "priority": "gold",
  "description": "Python FastAPI Dockerfile with slim base image"
}
```

**Validation endpoints:**

- `POST /validate/dockerfile` — Checks for public registry references, required directives (FROM, EXPOSE, WORKDIR), and private registry usage
- `POST /validate/gitlabci` — Checks for `stages:` definition, public registry references, and build stage presence

---

### 3.3 OpenWebUI AI Tools (root-level Python scripts)

**Purpose:** These scripts register "tools" (function-calling plugins) into OpenWebUI so that the AI chatbot can call them during conversations. When a user asks "generate a pipeline for my Java project," the AI model calls these tool functions to interact with real infrastructure.

**How tool registration works:**

```python
# Each script follows this pattern:
from open_webui.models.tools import Tools, ToolForm, ToolMeta

# 1. Define the tool function as an embedded string
content = textwrap.dedent('''
    class Tools:
        def my_function(self, param: str) -> dict:
            """Tool description for the AI model"""
            # ... actual logic ...
            return {"result": "..."}
''')

# 2. Register it in OpenWebUI
form = ToolForm(id="my_tool", name="My Tool", content=content, meta=meta)
tool = Tools.insert_new_tool(USER_ID, form, specs)
```

**Key tools:**

| Script | Tool ID | What it does |
|---|---|---|
| `create_pipeline_tool.py` | `gitlab_pipeline_generator` | Generates GitLab CI pipeline YAML for 7 technology stacks (Java, Python, Node, Go, PHP, .NET, Rust). Queries Nexus registry in real-time to find available images for each stage. Returns stage-by-stage configuration with available images. |
| `create_project_validator_tool.py` | `project_validator` | Validates that projects exist in SonarQube, GitLab, and Nexus. If a project is missing, generates escalation tickets with step-by-step creation guides for the specific platform. Supports Redmine, Jira, ServiceNow, and GitLab Issues as ticketing backends. Also validates full SonarQube configuration (quality gates, profiles, metrics, issues). |
| `gitlab_commit_tool.py` | `gitlab_commit_deploy` | Commits a Dockerfile and `.gitlab-ci.yml` directly to a GitLab repository and triggers the CI/CD pipeline. Can create new projects if they don't exist. Returns commit SHA and pipeline URL. |
| `fix_pipeline_tool.py` | — | Fixes issues in generated pipeline YAML |
| `fix_docker_tool.py` | — | Fixes issues in generated Dockerfiles |
| `fix_nexus_tool.py` | — | Troubleshoots Nexus registry connection problems |
| `fix_pipeline_sonar.py` | — | Fixes SonarQube integration in pipelines |
| `create_image_versions_tool.py` | — | Manages available image versions in the registry |
| `docker_health_check.py` | — | Checks Docker service health across the platform |

**Typical user conversation flow through OpenWebUI:**

```
User: "Create a CI/CD pipeline for my Java Spring Boot application
       and deploy it to my GitLab project my-team/legacy-app"

AI thinks: I need to:
  1. Call gitlab_pipeline_generator.get_pipeline_template(technology="java", stages="all")
  2. Call project_validator.validate_project(project_key="my-team/legacy-app", platform="gitlab")
  3. Generate the .gitlab-ci.yml from the template data
  4. Call gitlab_commit_deploy.commit_and_deploy(
       project_name="legacy-app",
       dockerfile_content="...",
       gitlab_ci_content="...",
       repo_url="http://gitlab-server/my-team/legacy-app"
     )
  5. Return the pipeline URL to the user
```

---

### 3.4 Project Management / Ticketing (`plane/`)

**Purpose:** Provides a Redmine-based ticketing system for handling escalation requests. When automated validation fails (e.g., a SonarQube project doesn't exist), the system creates tickets in Redmine for the DevOps team to act on.

**Components:**

| File | What it does |
|---|---|
| `docker-compose.yml` | Runs Redmine 5 (Alpine) on port 8090 with PostgreSQL 15 backend. Connects to both `ticketing-net` (internal) and `ai-platform-net` (shared with other services) |
| `setup_redmine.rb` | Ruby script executed inside the Redmine Rails console. Enables the REST API, creates a `devops-requests` project with issue tracking/time tracking/wiki modules, and generates an API key for the admin user |
| `full_setup.rb` | Complete setup: creates trackers (Bug, Feature, Support, Task), issue statuses (New, In Progress, Resolved, Closed, Rejected), priorities (Low through Immediate), and assigns all trackers to the `devops-requests` project |
| `configure_project.rb` | Additional project configuration |
| `create_trackers.rb` | Standalone tracker creation script |
| `fix_trackers.rb` | Repair utility for tracker issues |
| `check_db.rb` | Database health check script |

**How escalation works:**

```
1. project_validator tool detects: "SonarQube project 'my-app' doesn't exist"

2. It generates an escalation response with:
   - Platform-specific creation guide (UI steps + API command)
   - Pre-filled ticket payload:
     Title: "[ProjectValidator] Create project and grant CI permissions: my-app"
     Description: Evidence, requested actions, business justification
     Acceptance criteria: Checklist items

3. The ticket can be:
   - Created automatically via Redmine REST API (using REDMINE_API_KEY)
   - Opened as a pre-filled link in Redmine/Jira/ServiceNow/GitLab Issues
```

---

### 3.5 GitLab CI/CD Runner (`gitlab-runner/`)

**Purpose:** Configuration for the GitLab runner that executes CI/CD pipelines.

| File | What it does |
|---|---|
| `config/gitlab-runner-docker-compose.yml` | Docker Compose file for running the GitLab runner |
| `config/config/config.toml` | Runner registration config pointing to the GitLab server |

The runner is configured for Docker-in-Docker (DinD) execution, which is required for building Docker images inside CI pipeline jobs.

---

### 3.6 Monitoring & Observability

**Purpose:** Full observability stack for monitoring all platform services.

**Stack (`monitoring-stack.yml`):**

| Service | Port | Purpose |
|---|---|---|
| **Prometheus** | 9090 | Metrics collection. Scrapes itself, node-exporter, cAdvisor, DCGM exporter, and Ollama every 15s |
| **Grafana** | 3000 | Dashboard UI. Pre-configured with Redis datasource plugin. Credentials: admin/admin |
| **Node Exporter** | 9100 | Host-level system metrics (CPU, memory, disk, network) |
| **cAdvisor** | 8082 | Container-level metrics. Runs privileged with Docker socket access |
| **DCGM Exporter** | 9400 | NVIDIA GPU metrics (requires GPU hardware with nvidia driver) |

**Prometheus scrape targets** (`monitoring/prometheus.yml`):
- `prometheus:9090` — Self-monitoring
- `node-exporter:9100` — System metrics
- `cadvisor:8080` — Container metrics
- `dcgm-exporter:9400` — GPU metrics
- `ollama:11434` — LLM inference metrics

---

### 3.7 Security Tooling

**Stack (`security-tools.yml`):**

| Service | Port | Purpose |
|---|---|---|
| **Trivy** | 8083 | Container and dependency vulnerability scanner. Runs in server mode. Used in CI pipelines to scan built Docker images for HIGH/CRITICAL vulnerabilities |
| **Loki** | 3100 | Log aggregation system. Collects logs from all services for centralized searching |
| **Jaeger** | 16686 (UI), 14268 (collector) | Distributed tracing. Tracks request flows across microservices |

**How Trivy is used in CI pipelines:**

```yaml
# In the "security" stage of every pipeline:
trivy_scan:
  stage: security
  services:
    - name: localhost:5001/apm-repo/demo/aquasec-trivy:latest
      alias: trivy-server
      command: ["server", "--listen", "0.0.0.0:8080"]
  script:
    - trivy image --server http://trivy-server:8080
      --severity HIGH,CRITICAL
      --insecure
      ${NEXUS_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:latest
  allow_failure: true   # Security scan failures don't block the pipeline
```

---

### 3.8 Nexus Private Registry (`nexus/`)

**Purpose:** Scripts for populating the private Nexus Docker registry with base images.

| Script | What it does |
|---|---|
| `push-images-to-nexus.sh` | Pulls common Docker images from public registries and pushes them to the private Nexus registry |
| `push-language-stacks-to-nexus.sh` | Specifically pushes language runtime images (Python, Node, Java, Go) |
| `push-to-apm-repo-demo.sh` | Pushes images to the `apm-repo/demo/` repository path in Nexus |

All images in Nexus follow the path format: `localhost:5001/apm-repo/demo/<image>:<tag>`

---

## 4. End-to-End Data Flow

Here's the complete flow when a developer asks the AI to modernize a legacy Java application:

```
Step 1: CONVERSATION
  Developer (via OpenWebUI): "Modernize my Java app at gitlab-server/team/legacy-app"

Step 2: VALIDATION
  AI calls project_validator.validate_project("team/legacy-app", "gitlab")
    -> Checks GitLab API: GET /api/v4/projects/team%2Flegacy-app
    -> Returns PASS: project exists
  AI calls project_validator.validate_project("team/legacy-app", "sonarqube")
    -> Checks SonarQube API: GET /api/projects/search?projects=team/legacy-app
    -> Returns FAIL: project missing
    -> Generates Redmine ticket payload with creation instructions

Step 3: PIPELINE GENERATION
  AI calls gitlab_pipeline_generator.get_pipeline_template("java", "all")
    -> Queries Nexus: GET /v2/_catalog -> finds available images
    -> For each stage, resolves the image:
       compile: localhost:5001/apm-repo/demo/maven:3.9-eclipse-temurin-17
       build:   localhost:5001/apm-repo/demo/kaniko-executor:debug
       test:    localhost:5001/apm-repo/demo/alpine-curl:latest
       sast:    localhost:5001/apm-repo/demo/maven:3.9-eclipse-temurin-17
       quality: localhost:5001/apm-repo/demo/maven:3.9-eclipse-temurin-17
       security:localhost:5001/apm-repo/demo/aquasec-trivy:latest (as service)
       push:    localhost:5001/apm-repo/demo/alpine-curl:latest
       notify:  localhost:5001/apm-repo/demo/alpine-curl:latest
    -> Returns complete stage configuration with available images

Step 4: DOCKERFILE GENERATION
  AI calls RAG Generator API: POST /generate/dockerfile
    -> ChromaDB vector search for "java spring application" -> finds java-v1 template
    -> Resolves base image: localhost:5001/apm-repo/demo/amazoncorretto:17-alpine-jdk
    -> Fills placeholders, validates no public registry references
    -> Returns Dockerfile with audit trail

Step 5: COMMIT & DEPLOY
  AI calls gitlab_commit_deploy.commit_and_deploy(
    project_name="legacy-app",
    dockerfile_content="...",
    gitlab_ci_content="...",
    repo_url="http://gitlab-server/team/legacy-app"
  )
    -> Checks if Dockerfile and .gitlab-ci.yml exist (create vs update)
    -> Creates commit via GitLab API
    -> Waits 3 seconds, then fetches pipeline status
    -> Returns: commit SHA, pipeline URL, pipeline status

Step 6: PIPELINE EXECUTION (in GitLab)
  compile_jar  -> Maven builds JAR artifact
  build_image  -> Kaniko builds Docker image, pushes to Nexus
  test_image   -> Verifies image exists in Nexus registry
  static_analysis -> SpotBugs + PMD analysis
  sonarqube    -> Code quality scan
  trivy_scan   -> Container vulnerability scan (HIGH/CRITICAL)
  push_to_nexus -> Tags image with release version
  notify_splunk -> Sends success/failure event to Splunk HEC

Step 7: RESPONSE
  AI tells the developer:
    "I've deployed your modernized pipeline. Here are the results:
     - Repository: http://gitlab-server/team/legacy-app
     - Commit: a1b2c3d4
     - Pipeline #42: running
     - Pipeline URL: http://gitlab-server/team/legacy-app/-/pipelines/42

     Note: SonarQube project doesn't exist yet. I've prepared a ticket
     for the DevOps team to create it."
```

---

## 5. Infrastructure & Networking

### Docker Networks

All services communicate over shared Docker bridge networks using container names as hostnames:

| Network | Purpose | Services |
|---|---|---|
| `modernization-network` | Core application services | FastAPI, PostgreSQL, Redis, Ollama, MinIO, ChromaDB |
| `ai-platform-net` | Cross-stack communication | Shared between monitoring, security, ticketing, and core stacks |
| `monitoring-network` | Observability services | Prometheus, Grafana, Node Exporter, cAdvisor, Loki, Jaeger |
| `ticketing-net` | Ticketing services | Redmine, Redmine-DB |

### Service Connection Map

| Service | Internal URL | External Port | Credentials |
|---|---|---|---|
| **FastAPI** (Modernization API) | `http://modernization-api:8000` | 8002 | None |
| **RAG Generator API** | `http://localhost:8080` | 8080 | None |
| **PostgreSQL** (Modernization DB) | `postgresql://postgres:postgres@postgres:5432/modernization` | — | postgres / postgres |
| **PostgreSQL** (Redmine DB) | `postgresql://redmine:redmine123@redmine-db:5432/redmine` | — | redmine / redmine123 |
| **Redis** | `redis://redis:6379/0` | — | No auth |
| **Ollama** (LLM) | `http://ollama:11434` | 11434 | None |
| **MinIO** (Object Storage) | `http://minio:9000` | 9000 | minioadmin / minioadmin |
| **ChromaDB** (Vector DB) | `http://chromadb:8000` | 8000 | None |
| **Nexus** (Docker Registry) | `http://ai-nexus:5001` | 5001 | admin / r |
| **Nexus** (Artifact Repo) | `http://ai-nexus:8081` | 8081 | admin / r |
| **SonarQube** | `http://ai-sonarqube:9000` | 9000 | Token-based |
| **GitLab** | `http://gitlab-server` | 80 | PAT token |
| **Redmine** | `http://redmine:3000` | 8090 | API key |
| **Prometheus** | `http://prometheus:9090` | 9090 | None |
| **Grafana** | `http://grafana:3000` | 3000 | admin / admin |
| **Trivy** | `http://trivy-server:8080` | 8083 | None |
| **Loki** | `http://loki:3100` | 3100 | None |
| **Jaeger** | `http://jaeger:16686` | 16686 | None |
| **Splunk HEC** | `http://ai-splunk:8088` | 8088 | HEC token |

---

## 6. Nexus Image Catalog

The file `rag-ai/catalog.json` contains all available base images in the private Nexus registry. Here are the key ones used for pipeline generation:

### Language Runtimes
| Catalog Key | Image Path | Selected Tag | Used For |
|---|---|---|---|
| `python` | `localhost:5001/apm-repo/demo/python` | `3.12-slim` | Python apps, CI test stages |
| `java` | `localhost:5001/apm-repo/demo/amazoncorretto` | `17-alpine-jdk` | Java app runtime |
| `node` | `localhost:5001/apm-repo/demo/node` | `20-alpine` | Node.js apps |
| `maven` | `localhost:5001/apm-repo/demo/maven` | `3.9-eclipse-temurin-17` | Java compilation & SAST |
| `temurin` | `localhost:5001/apm-repo/demo/eclipse-temurin` | `17-jdk` | Alternative Java runtime |

### Build & CI Tools
| Catalog Key | Image Path | Selected Tag | Used For |
|---|---|---|---|
| `kaniko-executor` | `localhost:5001/apm-repo/demo/kaniko-executor` | `latest` | Docker image builds (no daemon required) |
| `docker` | `localhost:5001/apm-repo/demo/docker` | `24-cli` | Docker CLI and DinD |
| `alpine-curl` | `localhost:5001/apm-repo/demo/alpine-curl` | `latest` | Lightweight HTTP tasks in CI stages |
| `aquasec-trivy` | `localhost:5001/apm-repo/demo/aquasec-trivy` | `latest` | Container vulnerability scanning |

### Infrastructure
| Catalog Key | Image Path | Selected Tag | Used For |
|---|---|---|---|
| `postgres` | `localhost:5001/apm-repo/demo/postgres` | `16-alpine` | Database services |
| `redis` | `localhost:5001/apm-repo/demo/redis-7-alpine` | `demo-05` | Caching |
| `nginx` | `localhost:5001/apm-repo/demo/nginx` | `1.27-alpine` | Reverse proxy |
| `mongo` | `localhost:5001/apm-repo/demo/mongo` | `7` | Document database |
| `rabbitmq` | `localhost:5001/apm-repo/demo/rabbitmq` | `3-alpine` | Message broker |

The catalog is refreshed by running `catalog_refresh.py`, which queries `Nexus /v2/_catalog` API and applies tag selection rules per stack (e.g., prefer `3.12-slim` for Python, `20-alpine` for Node).

---

## 7. Golden Rules — Non-Negotiable Constraints

These rules (from `rag-ai/rag_corpus/rag_specs/golden_rules.md`) are enforced on every generated artifact:

### 1. Private Registry Only
- **NEVER** use public Docker Hub, GHCR, Quay.io, or MCR images
- **ALL** base images must come from: `localhost:5001/apm-repo/demo/<image>:<tag>`
- Validation blocks any `FROM python:`, `FROM node:`, `FROM openjdk:`, `docker.io`, `ghcr.io`

### 2. No Imagination / No Guessing
- Tags must come from the actual Nexus catalog — never invent tags
- Pipeline stages must use stored templates — never invent stages
- If a template is missing, return `TEMPLATE_MISSING` error (don't generate from scratch)

### 3. No Hardcoded Secrets
- Secrets must never appear in Dockerfiles or CI files
- Use GitLab CI variables (`${NEXUS_PASSWORD}`, `${SONARQUBE_TOKEN}`)
- Use environment variables for service credentials

### 4. Required Pipeline Stages
Every generated pipeline must include:
- `build` — Compile/package the application
- `security_scan` — bandit/safety/gitleaks/semgrep
- `code_quality` — SonarQube analysis
- `docker_build` — Build container image
- `docker_scan` — Trivy/Grype vulnerability scan
- `docker_push` — Push to Nexus registry

### 5. Validation Gates
Before returning any generated file:
- Validate YAML syntax (for CI files)
- Validate Dockerfile syntax (FROM, EXPOSE, WORKDIR present)
- Block any public registry FROM statements
- Ensure all required stages are present

### 6. Audit & Observability
Every generation must log:
- `request_id`, `template_id`, `base_image`, `tag`, `validation_result`
- Return audit data with: template used, generation timestamp, base image resolved

---

## 8. How to Run Everything

### Prerequisites
- Docker and Docker Compose installed
- At least 16GB RAM (Ollama + all services)
- GPU recommended for Ollama LLM inference (NVIDIA with DCGM)

### Step 1: Create Docker Networks
```bash
docker network create modernization-network
docker network create ai-platform-net
docker network create monitoring-network
```

### Step 2: Start Core Services
```bash
# Start the modernization API and its dependencies
cd legacy-modernization-api
docker-compose up -d

# Start the monitoring stack
docker-compose -f monitoring-stack.yml up -d

# Start security tools
docker-compose -f security-tools.yml up -d

# Start Redmine ticketing
cd plane
docker-compose up -d
```

### Step 3: Set Up ChromaDB and Ingest Templates
```bash
# Ensure ChromaDB is running (part of the core stack)
# Create collections
cd rag-ai
python create_collections.py

# Ingest templates into ChromaDB
python ingest_templates.py

# Refresh Nexus catalog
python catalog_refresh.py

# Start the RAG generator API
uvicorn generator_api:app --host 0.0.0.0 --port 8080
```

### Step 4: Set Up Redmine
```bash
# Execute inside the Redmine container's Rails console:
docker exec -i redmine rails runner - < plane/setup_redmine.rb
docker exec -i redmine rails runner - < plane/full_setup.rb
```

### Step 5: Register OpenWebUI Tools
```bash
# Run inside the OpenWebUI environment:
python create_pipeline_tool.py
python create_project_validator_tool.py
python gitlab_commit_tool.py
```

### Step 6: Run the FastAPI Service Locally (for development)
```bash
cd legacy-modernization-api
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Swagger UI: http://localhost:8000/docs
```

---

## 9. API Reference

### Modernization API (port 8000/8002)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Root — returns service name, version, status |
| `GET` | `/api/v1/health` | Health check with CPU/memory stats |
| `GET` | `/api/v1/health/ready` | Kubernetes readiness probe (stub) |
| `GET` | `/api/v1/health/live` | Kubernetes liveness probe (stub) |
| `POST` | `/api/v1/analysis/start` | Start analysis job. Body: `{ repository_url, branch, analysis_type }` |
| `GET` | `/api/v1/analysis/{job_id}` | Get analysis job status |
| `GET` | `/api/v1/analysis?skip=0&limit=10` | List all analysis jobs (paginated) |

### RAG Generator API (port 8080)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Root — API status and version |
| `GET` | `/health` | Health check — ChromaDB connectivity, template counts, catalog stacks |
| `GET` | `/collections` | List ChromaDB collections with document counts |
| `GET` | `/catalog` | View all available base images from Nexus |
| `GET` | `/catalog/{stack}` | Get catalog entry for a specific stack (java, python, node) |
| `POST` | `/generate/dockerfile` | Generate Dockerfile. Body: `{ stack, framework?, port?, workdir? }` |
| `POST` | `/generate/gitlabci` | Generate GitLab CI. Body: `{ stack, build_tool? }` |
| `POST` | `/validate/dockerfile` | Validate Dockerfile. Body: `{ content: "<dockerfile>" }` |
| `POST` | `/validate/gitlabci` | Validate GitLab CI. Body: `{ content: "<yaml>" }` |

---

## 10. File-by-File Reference

### Root-Level Configuration Files

| File | Purpose |
|---|---|
| `.gitignore` | Excludes `.env`, `__pycache__`, `chroma_data/`, `*.pyc`, `node_modules/`, `htmlcov/`, `*.egg-info` |
| `monitoring-stack.yml` | Docker Compose for Prometheus + Grafana + Node Exporter + cAdvisor + DCGM Exporter |
| `security-tools.yml` | Docker Compose for Trivy + Loki + Jaeger |
| `runner-config.toml` | GitLab runner TOML configuration |
| `isort-report.txt` | Python import sorting report |

### Root-Level Python Scripts (OpenWebUI Tools & Utilities)

| File | Purpose |
|---|---|
| `create_pipeline_tool.py` | Registers pipeline generator tool in OpenWebUI |
| `create_project_validator_tool.py` | Registers project validator tool in OpenWebUI |
| `gitlab_commit_tool.py` | Registers commit & deploy tool in OpenWebUI |
| `create_pipeline_model.py` | Registers an AI model configuration for pipeline generation |
| `create_project_validator_model.py` | Registers an AI model for project validation |
| `attach_tool_to_models.py` | Links tools to specific AI models in OpenWebUI |
| `fix_pipeline_tool.py` | Tool for fixing pipeline YAML issues |
| `fix_docker_tool.py` | Tool for fixing Dockerfile issues |
| `fix_nexus_tool.py` | Tool for Nexus registry troubleshooting |
| `fix_pipeline_sonar.py` | Tool for fixing SonarQube pipeline integration |
| `deploy_project_validator.py` | Deployment script for project validator |
| `deploy_image_versions.py` | Deployment script for image version management |
| `update_models_final.py` | Updates AI model configurations |
| `update_model_prompts.py` | Updates system prompts for AI models |
| `update_system_prompt.py` | Updates system-level prompts |
| `update_strong_prompt.py` | Updates enhanced prompts |
| `update_suggestions.py` | Updates suggestion prompts shown in OpenWebUI |
| `update_nexus_tool.py` | Updates Nexus tool registration |
| `update_ruby_tools.py` | Updates Ruby-based tools |
| `add_suggestion_prompts.py` | Adds new suggestion prompts |
| `create_image_versions_tool.py` | Tool for managing image versions |
| `image_versions_content.py` | Image version data |
| `openwebui_dockerfile_generator.py` | Dockerfile generator for OpenWebUI |
| `dockerfile_generator_function.py` | Dockerfile generation logic |
| `docker_health_check.py` | Docker service health monitoring |
| `verify_suggestions.py` | Validates suggestion configurations |
| `verify_model.py` | Validates model setup |
| `get_model_config.py` | Retrieves model configuration |
| `read_prompts.py` | Reads prompt configurations |
| `check_models.py` | Checks model status |
| `pipeline_knowledge.py` | Pipeline knowledge base content |
| `debug_pipeline.py` | Pipeline debugging utility |
| `setup-fastapi.ps1` | PowerShell script for FastAPI project initialization |
| `register-runner.ps1` | PowerShell script for GitLab runner registration |
| `deploy_gitlab.sh` | Bash script for GitLab deployment |

### Root-Level Test Files

| File | Purpose |
|---|---|
| `test_project_validator.py` | Integration tests for project validator across SonarQube, GitLab, Nexus, Redmine |
| `test_pipeline_tool.py` | Integration tests for pipeline generator |
| `test_nexus_tool.py` | Integration tests for Nexus tool |
| `test_pipeline_yaml.py` | Tests for pipeline YAML generation |
| `test_ruby.py` | Tests for Ruby script execution |
| `test_ruby_pipeline.py` | Tests for Ruby pipeline integration |
| `test_sonar_stage.py` | Tests for SonarQube pipeline stage |

### Documentation

| File | Purpose |
|---|---|
| `.github/copilot-instructions.md` | AI coding guidelines (architecture overview, conventions, workflows) |
| `TEST_COVERAGE_ANALYSIS.md` | Detailed test gap analysis with improvement proposals |
| `sonarqube-projects.md` | SonarQube project credentials and dashboard URLs |
| `sonarqube-projects.csv` | SonarQube project data in CSV format |
| `CLAUDE.md` | AI assistant guide (project structure, build commands, patterns) |

---

## 11. Current Limitations & TODOs

### Unfinished Implementations

1. **Analysis background processing** (`analysis.py:28`) — The `process_analysis` background task is commented out. The API creates jobs but never actually runs analysis.

2. **Job persistence** (`analysis.py:43`) — Job status is not stored in PostgreSQL. The `get_analysis_status` endpoint returns a hardcoded "pending" response.

3. **Health probe connectivity** (`health.py:24`) — The readiness probe doesn't actually check database, Redis, or Ollama connectivity. It's a stub that always returns "ready."

4. **Analysis listing** (`analysis.py:54`) — The pagination endpoint returns an empty list. No database query is implemented.

### Test Coverage Gaps

- **Zero unit tests** across the entire codebase
- **No pytest integration** — all tests are custom scripts requiring live infrastructure
- **No mocking** — every test requires real SonarQube, GitLab, Nexus, and ChromaDB instances
- **`legacy-modernization-api/` is completely untested** — no tests for endpoints, config, models, or services
- See `TEST_COVERAGE_ANALYSIS.md` for detailed gap analysis

### Security Considerations

- CORS is configured with wildcard (`*`) — should be restricted for production
- Nexus password (`"r"`) appears in multiple files — should use environment variables exclusively
- SonarQube tokens appear in pipeline templates — should use CI variables
- Redis has no authentication configured
- MinIO uses default credentials (`minioadmin`)

### Architecture Gaps

- No authentication/authorization on either API (FastAPI or RAG Generator)
- No rate limiting on API endpoints
- No database migrations (SQLAlchemy is in requirements but no models or Alembic setup)
- No async/await for database operations (SQLAlchemy async not configured)
- ChromaDB connection in RAG generator hardcodes `localhost:8000` (not configurable via env var)
- RAG generator loads `catalog.json` at startup from a hardcoded relative path (`rag-ai/catalog.json`)
