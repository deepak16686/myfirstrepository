# System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER / CLIENT                                   │
│                        (API Request / Chat Interface)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEVOPS TOOLS BACKEND                                 │
│                            (FastAPI - Port 8003)                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Pipeline Router │  │   Chat Router   │  │     Health/Status Router    │  │
│  │  /api/v1/pipeline│  │  /api/v1/chat   │  │         /health             │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────────────────┘  │
│           │                    │                                             │
│           ▼                    ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    PIPELINE GENERATOR SERVICE                        │    │
│  │  - Repository Analysis                                               │    │
│  │  - Template Selection (RAG)                                          │    │
│  │  - LLM Generation                                                    │    │
│  │  - Validation & Guardrails                                           │    │
│  │  - Reinforcement Learning                                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
          │              │              │              │              │
          ▼              ▼              ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
    │  GitLab  │  │ ChromaDB │  │  Ollama  │  │  Nexus   │  │ SonarQube│
    │  Server  │  │  (RAG)   │  │  (LLM)   │  │ Registry │  │          │
    │  :8929   │  │  :8005   │  │  :11434  │  │  :5001   │  │  :9000   │
    └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## Component Details

### 1. DevOps Tools Backend (FastAPI)

**Purpose**: Central orchestration service for pipeline generation

**Key Responsibilities**:
- REST API for pipeline generation
- Repository analysis via GitLab API
- Template retrieval from ChromaDB
- LLM-based pipeline generation
- Reinforcement learning from pipeline results
- GitLab commit operations

**Technology**: Python 3.11, FastAPI, httpx (async HTTP)

### 2. GitLab Server

**Purpose**: Source code management and CI/CD execution

**Integration Points**:
- Repository file listing (`/api/v4/projects/:id/repository/tree`)
- File content retrieval (`/api/v4/projects/:id/repository/files/:path`)
- Branch creation (`/api/v4/projects/:id/repository/branches`)
- Commit operations (`/api/v4/projects/:id/repository/commits`)
- Pipeline status (`/api/v4/projects/:id/pipelines`)
- Job details (`/api/v4/projects/:id/jobs`)

### 3. ChromaDB (Vector Database)

**Purpose**: RAG (Retrieval Augmented Generation) storage

**Collections**:
| Collection | Purpose |
|------------|---------|
| `pipeline_templates` | Base pipeline templates by language/framework |
| `pipeline_feedback` | User corrections for learning |
| `successful_pipelines` | RL-stored successful configurations |

**Key Features**:
- Metadata-based filtering (language, framework)
- Document storage with embeddings
- UUID-based collection management (v2 API)

### 4. Ollama (LLM Server)

**Purpose**: AI model inference for pipeline generation

**Model Used**: `pipeline-generator-v5` (custom fine-tuned)

**Fallback**: Default templates when LLM unavailable

### 5. Nexus Repository Manager

**Purpose**: Private Docker registry for CI/CD images

**Registry Configuration**:
| Variable | Value | Usage |
|----------|-------|-------|
| `NEXUS_PULL_REGISTRY` | `localhost:5001` | Job image pulls (Docker Desktop) |
| `NEXUS_INTERNAL_REGISTRY` | `ai-nexus:5001` | Kaniko pushes (container network) |

**Image Path**: `{registry}/apm-repo/demo/{image}:{tag}`

### 6. SonarQube

**Purpose**: Code quality analysis in `quality` stage

**Integration**: Sonar Scanner CLI via pipeline job

### 7. Trivy Server

**Purpose**: Container security scanning in `security` stage

**Mode**: Server mode as GitLab service container

### 8. Splunk

**Purpose**: Pipeline notifications and logging

**Integration**: HTTP Event Collector (HEC) in `notify` stage

---

## Data Flow Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           PIPELINE GENERATION FLOW                          │
└────────────────────────────────────────────────────────────────────────────┘

1. REQUEST
   User → POST /api/v1/pipeline/workflow

2. REPOSITORY ANALYSIS
   Backend → GitLab API → Analyze files, detect language/framework

3. TEMPLATE RETRIEVAL (RAG Priority)
   ┌─────────────────────────────────────────────────────────────────────┐
   │  Priority 1: RL Successful Pipelines (ChromaDB: successful_pipelines)│
   │  Priority 2: Language+Framework Template (ChromaDB: pipeline_templates)│
   │  Priority 3: Language-only Template                                  │
   │  Priority 4: Built-in Default Template                               │
   └─────────────────────────────────────────────────────────────────────┘

4. PIPELINE GENERATION
   ┌────────────────────────────────────────────────────────────────────┐
   │  If use_template_only=true:                                        │
   │    → Use default template directly                                 │
   │  Else:                                                             │
   │    → Send to Ollama LLM with context                              │
   │    → Validate & fix generated pipeline                            │
   └────────────────────────────────────────────────────────────────────┘

5. ENSURE RL STAGE
   Backend → Add "learn" stage if not present

6. COMMIT TO GITLAB
   Backend → Create branch → Commit .gitlab-ci.yml + Dockerfile

7. BACKGROUND RL MONITORING
   ┌────────────────────────────────────────────────────────────────────┐
   │  Background Task monitors pipeline every 30 seconds                │
   │  On success: Store configuration in ChromaDB                       │
   │  On failure: Log for analysis                                      │
   └────────────────────────────────────────────────────────────────────┘
```

---

## Network Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DOCKER NETWORK                                    │
│                         (devops-tools-network)                               │
│                                                                              │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │ devops-tools-   │     │    chromadb     │     │     ollama      │       │
│  │    backend      │────▶│                 │     │                 │       │
│  │   :8003         │     │   :8000         │     │   :11434        │       │
│  └────────┬────────┘     └─────────────────┘     └─────────────────┘       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │  gitlab-server  │     │    ai-nexus     │     │  ai-sonarqube   │       │
│  │   :80 (8929)    │     │   :5001/:8081   │     │   :9000         │       │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘       │
│                                                                              │
│  ┌─────────────────┐     ┌─────────────────┐                                │
│  │  trivy-server   │     │   ai-splunk     │                                │
│  │   :8080 (8083)  │     │   :8088         │                                │
│  └─────────────────┘     └─────────────────┘                                │
└─────────────────────────────────────────────────────────────────────────────┘

External Access (localhost):
  - Backend API:    localhost:8003
  - GitLab:         localhost:8929
  - ChromaDB:       localhost:8005
  - Nexus Registry: localhost:5001
  - Nexus UI:       localhost:8081
  - SonarQube:      localhost:9000
  - Splunk:         localhost:8088
```

---

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CREDENTIALS MANAGEMENT                               │
└─────────────────────────────────────────────────────────────────────────────┘

1. BACKEND SERVICE (.env file)
   ├── GITLAB_TOKEN        → GitLab API access
   ├── NEXUS_USERNAME      → Registry authentication
   ├── NEXUS_PASSWORD      → Registry authentication
   ├── SONARQUBE_PASSWORD  → SonarQube admin
   └── SPLUNK_HEC_TOKEN    → Splunk logging (optional)

2. GITLAB CI/CD VARIABLES (per-project)
   ├── NEXUS_USERNAME      → Used by Kaniko for pushes
   ├── NEXUS_PASSWORD      → Used by Kaniko for pushes (masked)
   ├── SONAR_TOKEN         → SonarQube analysis (masked)
   ├── SPLUNK_HEC_TOKEN    → Splunk notifications (masked)
   └── GITLAB_TOKEN        → RL API calls (masked)

3. PIPELINE RUNTIME
   ├── Images pulled from: localhost:5001 (NEXUS_PULL_REGISTRY)
   ├── Images pushed to:   ai-nexus:5001 (NEXUS_INTERNAL_REGISTRY)
   └── Kaniko auth:        /kaniko/.docker/config.json
```

---

## Scalability Considerations

### Horizontal Scaling

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    Backend 1    │ │    Backend 2    │ │    Backend 3    │
│     :8003       │ │     :8003       │ │     :8003       │
└─────────────────┘ └─────────────────┘ └─────────────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
              ┌─────────────────────────────┐
              │   Shared Services (Single)  │
              │  ChromaDB, GitLab, Ollama   │
              └─────────────────────────────┘
```

### State Management

- **Stateless Backend**: All state stored in ChromaDB/GitLab
- **Background Tasks**: Use distributed task queue (Celery) in production
- **Session Data**: Move to Redis for multi-instance support
