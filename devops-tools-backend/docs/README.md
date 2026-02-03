# DevOps Tools Backend - Documentation

## Overview

The DevOps Tools Backend is an AI-powered CI/CD pipeline generation system that automatically creates GitLab CI/CD pipelines and Dockerfiles based on repository analysis. It features **Reinforcement Learning (RL)** to continuously improve pipeline quality based on real execution results.

## Table of Contents

1. [Architecture Overview](./ARCHITECTURE.md)
2. [API Reference](./API.md)
3. [Credentials & Integration](./CREDENTIALS.md)
4. [Sequence Diagrams](./DIAGRAMS.md)
5. [Reinforcement Learning](./REINFORCEMENT_LEARNING.md)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- GitLab Server (self-hosted or GitLab.com)
- Nexus Repository Manager (for Docker images)
- ChromaDB (for RAG/Vector storage)
- Ollama (for LLM inference)

### Environment Variables

```bash
# GitLab
GITLAB_URL=http://gitlab-server
GITLAB_TOKEN=glpat-xxxxx

# ChromaDB
CHROMADB_URL=http://chromadb:8000

# Ollama
OLLAMA_URL=http://ollama:11434

# Nexus
NEXUS_URL=http://ai-nexus:8081
NEXUS_USERNAME=admin
NEXUS_PASSWORD=admin123

# SonarQube
SONARQUBE_URL=http://ai-sonarqube:9000

# Splunk
SPLUNK_HEC_URL=http://ai-splunk:8088
```

### Starting the Service

```bash
cd devops-tools-backend
docker-compose up -d --build
```

### API Endpoint

The service runs on `http://localhost:8003`

## Key Features

### 1. AI Pipeline Generation
- Analyzes repository structure (language, framework, files)
- Generates optimized `.gitlab-ci.yml` with 9 stages
- Creates multi-stage Dockerfiles using private Nexus registry

### 2. Reinforcement Learning
- Stores successful pipeline configurations in ChromaDB
- Prioritizes proven configurations for future generations
- Visible "learn" stage in GitLab pipelines

### 3. 9-Stage Pipeline
```
compile → build → test → sast → quality → security → push → notify → learn
```

### 4. Supported Languages
- Go (golang)
- Python
- Java (Maven)
- JavaScript/Node.js

## Architecture Components

| Component | Purpose | Port |
|-----------|---------|------|
| devops-tools-backend | Main API service | 8003 |
| GitLab Server | Source code & CI/CD | 8929 |
| ChromaDB | Vector database for RAG | 8005 |
| Ollama | LLM inference | 11434 |
| Nexus | Docker registry | 5001 |
| SonarQube | Code quality | 9000 |
| Trivy | Security scanning | 8083 |
| Splunk | Logging & notifications | 8088 |

## Usage Example

### Generate and Commit Pipeline

```bash
curl -X POST "http://localhost:8003/api/v1/pipeline/workflow" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "http://gitlab-server/root/my-go-app",
    "gitlab_token": "glpat-xxxxx",
    "auto_commit": true,
    "use_template_only": true
  }'
```

### Response

```json
{
  "success": true,
  "generation": {
    "gitlab_ci": "stages:\n  - compile\n  ...",
    "dockerfile": "FROM ...",
    "analysis": {
      "language": "go",
      "framework": "generic"
    }
  },
  "commit": {
    "branch": "feature/ai-pipeline-20260203-123456",
    "commit_id": "abc123..."
  },
  "pipeline": {
    "rl_enabled": true,
    "message": "Pipeline triggered. Reinforcement learning enabled."
  }
}
```

## File Structure

```
devops-tools-backend/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration management
│   ├── routers/
│   │   ├── pipeline.py         # Pipeline generation endpoints
│   │   └── chat.py             # Chat interface endpoints
│   ├── services/
│   │   ├── pipeline_generator.py  # Core pipeline generation logic
│   │   └── chat_service.py     # Chat orchestration
│   └── integrations/
│       ├── chromadb.py         # ChromaDB client
│       ├── ollama.py           # Ollama LLM client
│       └── base.py             # Base integration class
├── docs/                       # Documentation
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## License

Internal use only.
