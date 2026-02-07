# API Reference

Base URL: `http://localhost:8003/api/v1`

## Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/pipeline/analyze` | Analyze repository structure |
| POST | `/pipeline/generate` | Generate pipeline files |
| POST | `/pipeline/commit` | Commit files to GitLab |
| POST | `/pipeline/status` | Get pipeline status |
| POST | `/pipeline/workflow` | Full workflow (analyze → generate → commit) |
| POST | `/pipeline/feedback` | Store correction feedback |
| GET | `/pipeline/feedback/history` | Get feedback history |
| POST | `/pipeline/learn/record` | Record pipeline result for RL |
| GET | `/pipeline/learn/successful` | Get successful pipelines |
| GET | `/pipeline/learn/best` | Get best configuration |

---

## Pipeline Endpoints

### POST /pipeline/analyze

Analyze a GitLab repository to detect language, framework, and structure.

**Request Body**:
```json
{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx"
}
```

**Response**:
```json
{
  "success": true,
  "analysis": {
    "project_id": 9,
    "project_name": "my-app",
    "default_branch": "main",
    "files": [".gitignore", "main.go", "go.mod", "go.sum"],
    "language": "go",
    "framework": "generic",
    "package_manager": "go modules",
    "has_dockerfile": false,
    "has_gitlab_ci": false
  }
}
```

---

### POST /pipeline/generate

Generate `.gitlab-ci.yml` and `Dockerfile` for a repository.

**Request Body**:
```json
{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx",
  "additional_context": "Use Python 3.12",
  "model": "pipeline-generator-v5",
  "use_template_only": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| repo_url | string | Yes | GitLab repository URL |
| gitlab_token | string | Yes | GitLab access token |
| additional_context | string | No | Extra requirements |
| model | string | No | Ollama model (default: pipeline-generator-v5) |
| use_template_only | boolean | No | Skip LLM, use templates (default: false) |

**Response**:
```json
{
  "success": true,
  "gitlab_ci": "stages:\n  - compile\n  - build\n  ...",
  "dockerfile": "ARG BASE_REGISTRY=ai-nexus:5001\nFROM ...",
  "analysis": {
    "language": "go",
    "framework": "generic"
  },
  "model_used": "pipeline-generator-v5",
  "feedback_used": 3
}
```

---

### POST /pipeline/commit

Commit generated pipeline files to a new branch in GitLab.

**Request Body**:
```json
{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx",
  "gitlab_ci": "stages:\n  - compile\n  ...",
  "dockerfile": "FROM ...",
  "branch_name": "feature/ai-pipeline",
  "commit_message": "Add CI/CD pipeline [AI Generated]"
}
```

**Response**:
```json
{
  "success": true,
  "commit_id": "abc123def456",
  "branch": "feature/ai-pipeline-20260203-123456",
  "web_url": "http://gitlab-server/root/my-app/-/commit/abc123",
  "project_id": 9
}
```

---

### POST /pipeline/status

Get the status of the latest pipeline for a branch.

**Request Body**:
```json
{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx",
  "branch": "feature/ai-pipeline-20260203-123456"
}
```

**Response**:
```json
{
  "success": true,
  "pipeline_id": 215,
  "status": "success",
  "duration": 139,
  "stages": ["compile", "build", "test", "sast", "quality", "security", "push", "notify", "learn"],
  "jobs": [
    {"name": "compile", "status": "success", "duration": 15},
    {"name": "build_image", "status": "success", "duration": 45},
    {"name": "learn_record", "status": "success", "duration": 5}
  ],
  "web_url": "http://gitlab-server/root/my-app/-/pipelines/215"
}
```

---

### POST /pipeline/workflow

**Complete workflow**: Analyze → Generate → Commit → Monitor

This is the main endpoint for full automation.

**Request Body**:
```json
{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx",
  "additional_context": null,
  "model": "pipeline-generator-v5",
  "auto_commit": true,
  "branch_name": null,
  "use_template_only": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| repo_url | string | Yes | GitLab repository URL |
| gitlab_token | string | Yes | GitLab access token |
| additional_context | string | No | Extra requirements |
| model | string | No | Ollama model name |
| auto_commit | boolean | No | Auto-commit if true (default: false) |
| branch_name | string | No | Custom branch name |
| use_template_only | boolean | No | Skip LLM (default: false) |

**Response** (with auto_commit=true):
```json
{
  "success": true,
  "generation": {
    "gitlab_ci": "stages:\n  - compile\n  ...",
    "dockerfile": "FROM ...",
    "analysis": {
      "project_id": 9,
      "language": "go",
      "framework": "generic"
    },
    "model_used": "template-only",
    "feedback_used": 0
  },
  "commit": {
    "branch": "feature/ai-pipeline-20260203-123456",
    "commit_id": "abc123def456",
    "web_url": "http://gitlab-server/root/my-app/-/commit/abc123",
    "project_id": 9
  },
  "pipeline": {
    "message": "Pipeline triggered. Reinforcement learning enabled - results will be recorded automatically.",
    "branch": "feature/ai-pipeline-20260203-123456",
    "rl_enabled": true
  }
}
```

---

## Reinforcement Learning Endpoints

### POST /pipeline/learn/record

Manually record a pipeline result for RL learning.

**Request Body**:
```json
{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx",
  "branch": "feature/ai-pipeline-20260203-123456",
  "pipeline_id": 215
}
```

**Response**:
```json
{
  "success": true,
  "message": "Pipeline succeeded! Configuration stored for reinforcement learning.",
  "pipeline_id": 215,
  "status": "success",
  "stored": true
}
```

---

### GET /pipeline/learn/successful

Get successful pipeline configurations for a language/framework.

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| language | string | Yes | Programming language |
| framework | string | No | Framework name |
| limit | integer | No | Max results (default: 5) |

**Example**:
```
GET /pipeline/learn/successful?language=go&limit=2
```

**Response**:
```json
{
  "success": true,
  "language": "go",
  "framework": null,
  "pipelines": [
    {
      "id": "success_go_generic_617d9411be45",
      "language": "go",
      "framework": "generic",
      "pipeline_id": "211",
      "duration": 129,
      "stages_count": 8,
      "timestamp": "2026-02-03T08:04:50.209711"
    },
    {
      "id": "success_go_generic_717ca560783a",
      "language": "go",
      "framework": "generic",
      "pipeline_id": "215",
      "duration": 139,
      "stages_count": 9,
      "timestamp": "2026-02-03T08:20:02.127207"
    }
  ],
  "count": 2
}
```

---

### GET /pipeline/learn/best

Get the best performing pipeline configuration.

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| language | string | Yes | Programming language |
| framework | string | No | Framework name |

**Example**:
```
GET /pipeline/learn/best?language=go
```

**Response**:
```json
{
  "success": true,
  "language": "go",
  "framework": null,
  "config": "stages:\n  - compile\n  - build\n  ...",
  "source": "reinforcement_learning"
}
```

---

## Feedback Endpoints

### POST /pipeline/feedback

Store feedback from manual corrections for learning.

**Request Body**:
```json
{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx",
  "branch": "feature/ai-pipeline-20260203-123456",
  "original_gitlab_ci": "stages:\n  ...",
  "original_dockerfile": "FROM ...",
  "error_type": "missing_stage",
  "fix_description": "Added security scanning stage"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Feedback stored for reinforcement learning",
  "changes_detected": {
    "gitlab_ci": true,
    "dockerfile": false
  }
}
```

---

### GET /pipeline/feedback/history

Get stored feedback history.

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| language | string | No | Filter by language |
| framework | string | No | Filter by framework |
| limit | integer | No | Max results (default: 10) |

**Example**:
```
GET /pipeline/feedback/history?language=python&limit=5
```

**Response**:
```json
{
  "success": true,
  "feedback": [
    {
      "id": "feedback_123",
      "language": "python",
      "framework": "fastapi",
      "error_type": "wrong_base_image",
      "fix_description": "Changed to Python 3.11",
      "timestamp": "2026-02-01T10:30:00"
    }
  ],
  "count": 1
}
```

---

## Health Check

### GET /health

Check service health.

**Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "tools": {
    "gitlab": "healthy",
    "chromadb": "healthy",
    "ollama": "healthy",
    "nexus": "healthy"
  }
}
```

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes**:
| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad request (invalid input) |
| 404 | Resource not found |
| 500 | Internal server error |

---

## Rate Limiting

Currently no rate limiting is implemented. For production:
- Consider adding rate limiting per IP/token
- Implement request queuing for LLM operations
