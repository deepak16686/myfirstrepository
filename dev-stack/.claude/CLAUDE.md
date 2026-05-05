# AI DevOps Pipeline Platform — Claude Code Instructions

## Project Overview

This is an **AI-powered DevOps pipeline generation platform** that automatically creates CI/CD pipelines for GitLab CI, Jenkins, and GitHub Actions using LLM (Ollama/Claude) with RAG-based template matching from ChromaDB.

**Project root**: `D:/Repos/ai-folder/dev-stack`

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend (chatbot-portal :3005)                              │
│  React chat UI for pipeline generation                        │
├──────────────────────────────────────────────────────────────┤
│  Backend API (devops-tools-backend :8003)                     │
│  FastAPI — Python 3.12                                        │
│  Routers: pipeline, jenkins, github, chat, terraform, etc.    │
├──────────────────────────────────────────────────────────────┤
│  LLM Layer                                                    │
│  Ollama :11434 (qwen3:32b) OR Claude Code CLI                │
│  ChromaDB :8005 (RAG template store)                          │
├──────────────────────────────────────────────────────────────┤
│  Git Servers                                                  │
│  GitLab :8929 (GitLab CI pipelines)                           │
│  Gitea :3002 (Jenkins + GitHub Actions repos)                 │
├──────────────────────────────────────────────────────────────┤
│  CI/CD Engines                                                │
│  Jenkins :8080/jenkins (Multibranch pipelines)                │
│  Gitea Actions Runner (GitHub Actions-compatible)             │
│  GitLab Runner (GitLab CI)                                    │
├──────────────────────────────────────────────────────────────┤
│  Quality & Security                                           │
│  SonarQube :9002 | Nexus :8181/:5001 | Trivy :8183           │
├──────────────────────────────────────────────────────────────┤
│  Monitoring & Observability                                   │
│  Prometheus :9090 | Grafana :3000 | Loki :3100                │
│  Jaeger :16686 | Splunk :10000 | cAdvisor :8182               │
├──────────────────────────────────────────────────────────────┤
│  Infrastructure                                               │
│  Vault :8200 | Redis :6379 | PostgreSQL :5432                 │
│  MinIO :9001 | Qdrant :6333 | Nginx Proxy :8443              │
├──────────────────────────────────────────────────────────────┤
│  Project Management                                           │
│  Jira :8180 | Redmine :8090                                   │
└──────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
dev-stack/
├── backend/                    # FastAPI backend (Python 3.12)
│   ├── app/
│   │   ├── routers/            # API endpoints
│   │   ├── services/           # Business logic
│   │   │   ├── pipeline/       # GitLab CI pipeline generator
│   │   │   ├── jenkins_pipeline/ # Jenkins pipeline generator
│   │   │   ├── github_pipeline/  # GitHub Actions generator
│   │   │   ├── terraform/      # Terraform module generator
│   │   │   ├── secret_manager/ # Vault integration
│   │   │   └── shared/         # Shared utilities
│   │   ├── integrations/       # LLM provider factory
│   │   ├── models/             # Pydantic schemas
│   │   ├── prompts/            # System prompts for LLM
│   │   └── config.py           # Settings (env vars + Vault)
│   ├── frontend/               # Static HTML/JS chat UI
│   ├── Dockerfile
│   └── requirements.txt
├── chatbot-portal/             # React chat frontend (:3005)
├── infrastructure/
│   ├── docker-compose.yml      # ALL 42 services
│   ├── vault-config.hcl        # Vault server config
│   ├── nginx/                  # Reverse proxy configs
│   └── postgres-init/          # DB init scripts
├── monitoring/
│   └── prometheus.yml          # Scrape targets
├── source-control/             # Gitea runner config
└── documentation/
    ├── dev-stack-dashboard.html # Service dashboard
    └── architecture-diagram.html
```

---

## Key Technical Details

### Backend API (port 8003)
- **Framework**: FastAPI with Uvicorn
- **Language**: Python 3.12
- **Config**: `app/config.py` — reads from Vault first, falls back to env vars
- **LLM**: Switchable via `LLM_PROVIDER` env var (`ollama` or `claude-code`)
- **Pipeline generators**: Separate packages under `app/services/` for each CI system
- **Chat pattern**: URL detection → generate pipeline → approval → commit → monitor build

### Git Servers
- **GitLab** (`gitlab-server:80` internal, `localhost:8929` external): GitLab CI repos
- **Gitea** (`gitea-server:3000` internal, `localhost:3002` external): Jenkins + GitHub Actions repos
  - Org `jenkins-projects/` — Jenkins multibranch repos
  - Org `github-projects/` — Gitea Actions repos

### Docker Networking
- Container-to-container: use service names (e.g., `gitlab-server`, `gitea-server`, `jenkins-master:8080/jenkins`)
- Host access: use `localhost:{port}`
- Nexus registry: `localhost:5001` (host) / `ai-nexus:5001` (containers, BUT Dockerfiles must use `localhost:5001`)
- Networks: `ai-platform-net`, `gitlab-net`, `jenkins-net`, `monitoring-network`, `ticketing-net`

### Vault (HashiCorp)
- **Mode**: Server with file storage (persistent across restarts)
- **Root token**: Stored at `/vault/file/.root-token` inside container
- **Auto-unseal**: `vault-unseal` sidecar polls every 10s
- **Secret paths**: `secret/{service-name}` (KV-v2)
- **Backend reads token** from mounted volume, no env var needed

### ChromaDB (RAG Store)
- **API**: v2 (`/api/v2/...`) — v1 is deprecated
- Collections: `gitlab_successful_pipelines`, `jenkins_successful_pipelines`, `github_actions_successful_pipelines`, `jenkins_pipeline_templates`
- Template ID format: `manual_{language}_{framework}_{content_hash[:12]}`

---

## Critical Rules

### DO
- Always use internal Docker DNS names in service-to-service code (`gitlab-server`, `gitea-server`, etc.)
- Use `localhost:{port}` for browser/host-facing URLs
- Check Vault for credentials before hardcoding
- Use multi-stage Docker builds for all services
- Test pipeline changes against actual runners (GitLab Runner, Jenkins agents, Gitea Actions Runner)
- Use `docker compose -p dev-stack` for all compose operations

### DON'T
- Don't use `apk add` in GitLab Runner DinD jobs (no internet) — use pre-built Nexus images
- Don't use `actions/checkout@v4` in Gitea Actions host jobs (cache corruption) — use shell git clone
- Don't use `docker/build-push-action` in Gitea Actions — use shell `docker build/push`
- Don't use ChromaDB API v1 endpoints
- Don't hardcode credentials — always use Vault or env vars
- Don't modify `.env` files directly — update Vault instead
- Don't use `:latest` Docker tags — pin versions

### Common Gotchas
- Jenkins URL must include `/jenkins` context path: `http://jenkins-master:8080/jenkins`
- Gitea token auth format: `token {token}` (NOT `Bearer {token}`)
- Gitea file update requires SHA of existing file content
- YAML `on:` key becomes boolean `True` after `safe_load` — must post-fix
- LLM output often wrapped in code fences — strip before parsing
- Spring Boot Gradle produces both fat jar + `-plain.jar` — filter in Dockerfile

---

## Service Ports Quick Reference

| Port  | Service              | Port  | Service              |
|-------|----------------------|-------|----------------------|
| 3000  | Grafana              | 8200  | Vault                |
| 3001  | ChromaDB Admin       | 8443  | Nginx Proxy          |
| 3002  | Gitea                | 9000  | MinIO API            |
| 3005  | Chatbot Portal       | 9001  | MinIO Console        |
| 3100  | Loki                 | 9002  | SonarQube            |
| 5001  | Nexus Docker Reg     | 9090  | Prometheus           |
| 5432  | PostgreSQL           | 9100  | Node Exporter        |
| 6333  | Qdrant               | 9400  | DCGM Exporter        |
| 6379  | Redis                | 10000 | Splunk               |
| 8003  | Backend API          | 11434 | Ollama               |
| 8005  | ChromaDB             | 14268 | Jaeger Collector     |
| 8080  | Jenkins              | 16686 | Jaeger UI            |
| 8088  | Splunk HEC           | 18080 | TaskFlow API GW      |
| 8090  | Redmine              | 18081 | TaskFlow Auth        |
| 8180  | Jira                 | 18082 | TaskFlow Task Svc    |
| 8181  | Nexus Web            | 18083 | TaskFlow Notify      |
| 8182  | cAdvisor             | 8025  | TaskFlow MailHog     |
| 8183  | Trivy                | 8929  | GitLab               |

---

## Credentials — From Vault

All credentials are stored in HashiCorp Vault at `secret/{service}`. See `CREDENTIALS.md` for full details.

**Key credentials** (verified 2026-04-07):
- **GitLab**: root / ${GITLAB_ROOT_PASSWORD} | token: ${GITLAB_TOKEN}
- **Gitea**: admin / admin123 | token: ${GITEA_TOKEN}
- **Jenkins**: admin / admin123 (context path: /jenkins)
- **SonarQube**: admin / ${SONARQUBE_ADMIN_PASSWORD} | token: ${SONARQUBE_TOKEN}
- **Nexus**: admin / r (registry: localhost:5001)
- **Grafana**: admin / admin123
- **Splunk**: admin / ${SPLUNK_PASSWORD}
- **Jira**: deepak16686 / admin123
- **Redmine**: admin / admin123
- **MinIO**: admin / admin123
- **PostgreSQL**: postgres / postgres
- **Vault root token**: ${VAULT_TOKEN}

---

## Working with the Backend

```bash
# Rebuild backend after code changes
docker compose -p dev-stack up -d --build devops-tools-backend

# View backend logs
docker logs -f devops-tools-backend

# Enter backend container
docker exec -it devops-tools-backend bash

# API docs
open http://localhost:8003/docs
```

## Working with Pipelines

```bash
# GitLab pipeline: push to repo → auto-triggers runner
# Jenkins pipeline: push to Gitea → trigger scan → multibranch build
# GitHub Actions: push to Gitea → Gitea Actions runner picks up workflow

# Monitor builds
curl http://localhost:8003/api/v1/pipeline/progress/{session_id}
curl http://localhost:8003/api/v1/jenkins-pipeline/progress/{session_id}
curl http://localhost:8003/api/v1/github-pipeline/progress/{session_id}
```
