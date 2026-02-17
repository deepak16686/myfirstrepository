# AI DevOps Platform

An AI-powered CI/CD pipeline generation platform that automatically creates GitLab CI/CD pipelines, GitHub Actions workflows, and Dockerfiles based on repository analysis. Features reinforcement learning from real pipeline executions to continuously improve generation quality.

## Features

- **Automatic Language Detection** -- Java, Python, Go, Rust, Node.js, Ruby, PHP, C#/.NET, Kotlin, Scala
- **GitLab CI/CD Generation** -- 9-stage pipeline: compile, build, test, SAST, quality, security, push, notify, learn
- **GitHub Actions Generation** -- Workflow files for Gitea/GitHub repositories
- **Multi-stage Dockerfiles** -- Build + runtime stages with Nexus private registry support
- **Reinforcement Learning** -- Stores successful pipeline configs in ChromaDB for future RAG retrieval
- **Self-Healing Pipelines** -- LLM-powered auto-fix for failed pipelines (max 3 retries)
- **Dry-Run Validation** -- YAML syntax, Dockerfile, GitLab CI lint, Nexus image checks before commit
- **Dual LLM Support** -- Ollama (qwen3:32b) or Claude Code CLI (Sonnet/Opus)
- **Chat Interface** -- Conversational pipeline generation with tool calling
- **13 Tool Integrations** -- GitLab, Gitea, SonarQube, Trivy, Nexus, Ollama, ChromaDB, Splunk, Jenkins, Jira, PostgreSQL, Redis

## Architecture

```
User -> Frontend (HTML/JS) -> FastAPI Backend (:8003) -> LLM Provider (Ollama/Claude)
                                    |                          |
                                    +-- GitLab (CI/CD exec)    +-- ChromaDB (RAG/RL)
                                    +-- SonarQube (Quality)    +-- Nexus (Registry)
                                    +-- Trivy (Security)       +-- Splunk (Logging)
                                    +-- Jira (Tickets)         +-- Jenkins (CI/CD alt)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation and [infographic-documentation/](infographic-documentation/) for visual diagrams.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- External networks: `ai-platform-net`, `gitlab-net`
- Running services: GitLab, Ollama, ChromaDB (minimum)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/your-org/devops-tools-backend.git
cd devops-tools-backend
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Start the application:
```bash
docker-compose up -d
```

4. Access the platform:
- **Web UI**: http://localhost:8003
- **API Docs**: http://localhost:8003/docs
- **Health Check**: http://localhost:8003/health

## Configuration

All configuration is managed through environment variables. See [.env.example](.env.example) for the complete list.

| Variable | Description | Required |
|----------|-------------|----------|
| `GITLAB_URL` | GitLab server URL | Yes |
| `GITLAB_TOKEN` | GitLab API token | Yes |
| `OLLAMA_URL` | Ollama LLM server | Yes |
| `CHROMADB_URL` | ChromaDB vector database | Yes |
| `LLM_PROVIDER` | `ollama` or `claude-code` | No (default: ollama) |
| `NEXUS_URL` | Nexus registry URL | No |
| `SONARQUBE_URL` | SonarQube server | No |
| `TRIVY_URL` | Trivy scanner | No |

See [docs/CREDENTIALS.md](docs/CREDENTIALS.md) for detailed credential setup.

## Project Structure

```
devops-tools-backend/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Pydantic settings & tool configuration
│   ├── integrations/              # External tool API clients (13 integrations)
│   │   ├── base.py                # Abstract base integration
│   │   ├── ollama.py              # Ollama LLM API
│   │   ├── claude_code.py         # Claude Code CLI integration
│   │   ├── llm_provider.py        # Factory pattern for LLM selection
│   │   ├── chromadb.py            # Vector DB for RAG & templates
│   │   ├── gitlab.py              # GitLab API
│   │   ├── github.py              # GitHub/Gitea API
│   │   └── ...                    # sonarqube, trivy, nexus, jira, splunk, jenkins
│   ├── models/
│   │   ├── schemas.py             # Pydantic models (shared)
│   │   └── pipeline_schemas.py    # Pipeline-specific request/response models
│   ├── prompts/
│   │   └── pipeline_system_prompt.txt  # LLM system prompt
│   ├── routers/                   # API endpoint handlers
│   │   ├── pipeline.py            # Pipeline generation endpoints
│   │   ├── chat.py                # Chat interface endpoints
│   │   ├── github_pipeline.py     # GitHub Actions endpoints
│   │   ├── connectivity.py        # Tool health check endpoints
│   │   └── ...                    # gitlab, sonarqube, trivy, nexus, tools, unified
│   └── services/                  # Business logic
│       ├── pipeline/              # GitLab pipeline generation (modular package)
│       │   ├── analyzer.py        # Repository language/framework detection
│       │   ├── generator.py       # Core LLM-powered generation
│       │   ├── templates.py       # ChromaDB RAG template management
│       │   ├── validator.py       # Pipeline validation & guardrails
│       │   ├── default_templates.py  # Built-in CI/Dockerfile templates
│       │   ├── committer.py       # GitLab commit operations
│       │   ├── monitor.py         # Pipeline status monitoring
│       │   ├── learning.py        # Reinforcement learning feedback
│       │   └── constants.py       # Image maps & compile commands
│       ├── github_pipeline/       # GitHub Actions generation (modular package)
│       ├── chat_service.py        # Chat orchestration with tool calling
│       ├── self_healing_workflow.py  # Auto-fix failed pipelines
│       ├── llm_fixer.py           # LLM-based error fixing
│       └── ...                    # validators, fixers, progress tracking
├── frontend/                      # Web UI (HTML/CSS/JS)
├── docs/                          # Documentation
├── infographic-documentation/     # Architecture diagrams (SVG)
├── Dockerfile                     # Container build
├── docker-compose.yml             # Service orchestration
├── Modelfile.pipeline-generator-v5  # Ollama model configuration
└── requirements.txt               # Python dependencies
```

## API Reference

### Pipeline Generation
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/pipeline/generate` | Generate pipeline files |
| POST | `/api/v1/pipeline/generate-validated` | Generate with validation + auto-fix |
| POST | `/api/v1/pipeline/commit` | Commit to GitLab + start monitoring |
| POST | `/api/v1/pipeline/dry-run` | Validate without committing |
| POST | `/api/v1/pipeline/self-heal` | Self-healing pipeline workflow |

### Chat Interface
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/chat/` | Send message (with tool calling) |
| POST | `/api/v1/chat/new` | Create new conversation |
| GET | `/api/v1/chat/history/{id}` | Get conversation history |

### Reinforcement Learning
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/pipeline/learn/record` | Record pipeline result for RL |
| POST | `/api/v1/pipeline/learn/store-template` | Store proven template |
| GET | `/api/v1/pipeline/learn/successful` | Get successful configs |
| GET | `/api/v1/pipeline/learn/best` | Get best config for language |

### Tool Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/connectivity/` | Check all tool health |
| GET | `/api/v1/tools/` | List all tools with status |

See full API documentation at `/docs` (Swagger UI) or `/redoc` when the server is running.

## Integrations

| Tool | Purpose | Port |
|------|---------|------|
| GitLab | Source code & CI/CD execution | 8929 |
| Gitea/GitHub | GitHub Actions support | 3000 |
| Ollama | LLM inference (qwen3:32b) | 11434 |
| ChromaDB | Vector DB for RAG & RL | 8000 |
| SonarQube | Code quality analysis | 9000 |
| Trivy | Container vulnerability scanning | 8080 |
| Nexus | Docker image registry | 5001/8081 |
| Splunk | Event logging (HEC) | 8088 |
| Jenkins | Alternative CI/CD | 8080 |
| Jira | Issue tracking & access requests | 8080 |
| PostgreSQL | Database persistence | 5432 |
| Redis | Caching | 6379 |

## Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Credentials Setup](docs/CREDENTIALS.md)
- [Reinforcement Learning](docs/REINFORCEMENT_LEARNING.md)
- [Architecture Diagrams](docs/DIAGRAMS.md)
- [Pipeline Flow Diagrams](docs/AI_PIPELINE_FLOW_DIAGRAM.md)

## Tech Stack

- **Backend**: Python 3.11, FastAPI, Pydantic, httpx
- **LLM**: Ollama (qwen3:32b) / Claude Code CLI
- **Vector DB**: ChromaDB
- **Frontend**: HTML, CSS, JavaScript, Highlight.js, Marked.js
- **Deployment**: Docker, Docker Compose
- **CI/CD**: GitLab CI, GitHub Actions

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run validation: ensure imports resolve with `python -c "from app.main import app"`
5. Commit: `git commit -m "Add my feature"`
6. Push: `git push origin feature/my-feature`
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
