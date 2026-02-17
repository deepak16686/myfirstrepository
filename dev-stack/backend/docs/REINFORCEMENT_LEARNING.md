# Reinforcement Learning (RL) System

## Overview

The DevOps Tools Backend implements a Reinforcement Learning system that improves pipeline generation quality over time by learning from successful pipeline executions.

## How It Works

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      REINFORCEMENT LEARNING CYCLE                                │
└─────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │  GENERATE   │────────►│   EXECUTE   │────────►│   RECORD    │
    │  Pipeline   │         │  in GitLab  │         │  Results    │
    └─────────────┘         └─────────────┘         └──────┬──────┘
          ▲                                                │
          │                                                │
          │         ┌─────────────────────────┐           │
          └─────────│  LEARN & IMPROVE        │◄──────────┘
                    │  (ChromaDB Storage)     │
                    └─────────────────────────┘
```

## Components

### 1. ChromaDB Collection: `successful_pipelines`

Stores configurations that have been proven to work.

**Document Structure**:
```json
{
  "id": "success_go_generic_617d9411be45",
  "document": "## Successful Pipeline Configuration\nLanguage: go\n...",
  "metadata": {
    "language": "go",
    "framework": "generic",
    "pipeline_id": "211",
    "duration": 129,
    "stages_count": 9,
    "timestamp": "2026-02-03T08:04:50.209711"
  }
}
```

### 2. Background Monitor Task

Runs after each pipeline commit to track execution results.

```python
async def monitor_pipeline_for_learning(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    project_id: int,
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30
):
    """
    Background task that:
    1. Polls GitLab every 30 seconds
    2. Waits for pipeline completion (max 15 min)
    3. On success: Stores config in ChromaDB
    4. On failure: Logs for analysis
    """
```

### 3. Learn Stage (Visible in GitLab)

A dedicated pipeline stage that shows RL is active.

```yaml
learn_record:
  stage: learn
  image: curlimages-curl:latest
  script:
    - echo "REINFORCEMENT LEARNING - Recording Success"
    - echo "Pipeline ${CI_PIPELINE_ID} completed successfully!"
    - echo "This configuration will be stored for future AI pipeline generation"
  when: on_success
  allow_failure: true
```

---

## RL Priority System

When generating a new pipeline, the system checks sources in this order:

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | `successful_pipelines` | Proven configs from RL storage |
| 2 | `pipeline_templates` (exact) | Language + framework match |
| 3 | `pipeline_templates` (partial) | Language-only match |
| 4 | Built-in defaults | Hardcoded templates |

### Code Implementation

```python
async def get_reference_pipeline(self, language: str, framework: str) -> Optional[str]:
    """
    PRIORITY ORDER (Reinforcement Learning enabled):
    1. Best successful pipeline from RL (proven to work)
    2. Exact language + framework match from ChromaDB templates
    3. Language-only match from ChromaDB templates
    4. Built-in default template for the language (ALWAYS available)
    """

    # PRIORITY 1: Check for successful pipelines from reinforcement learning
    best_config = await self.get_best_pipeline_config(language, framework)
    if best_config:
        return self._ensure_learn_stage(best_config)

    # PRIORITY 2-3: Check ChromaDB templates
    # ... template lookup code ...

    # PRIORITY 4: Built-in default
    return self._ensure_learn_stage(self._get_default_gitlab_ci(analysis))
```

---

## API Endpoints

### Record Pipeline Result

```http
POST /api/v1/pipeline/learn/record
Content-Type: application/json

{
  "repo_url": "http://gitlab-server/root/my-app",
  "gitlab_token": "glpat-xxxxx",
  "branch": "feature/ai-pipeline-20260203-123456",
  "pipeline_id": 215
}
```

**Response (Success)**:
```json
{
  "success": true,
  "message": "Pipeline succeeded! Configuration stored for reinforcement learning.",
  "pipeline_id": 215,
  "status": "success",
  "stored": true
}
```

**Response (Failure)**:
```json
{
  "success": true,
  "message": "Pipeline failed. Result logged for analysis.",
  "pipeline_id": 215,
  "status": "failed",
  "stored": false
}
```

### Get Successful Pipelines

```http
GET /api/v1/pipeline/learn/successful?language=go&limit=5
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
    }
  ],
  "count": 1
}
```

### Get Best Configuration

```http
GET /api/v1/pipeline/learn/best?language=go&framework=generic
```

**Response**:
```json
{
  "success": true,
  "language": "go",
  "framework": "generic",
  "config": "stages:\n  - compile\n  - build\n  ...",
  "source": "reinforcement_learning"
}
```

---

## Data Storage

### ChromaDB Document Format

When a pipeline succeeds, the following is stored:

```markdown
## Successful Pipeline Configuration
Language: go
Framework: generic
Pipeline ID: 215
Duration: 139 seconds
Stages Passed: learn_record, notify_success, push, security, quality, sast, test, build_image, compile

### .gitlab-ci.yml
```yaml
stages:
  - compile
  - build
  - test
  - sast
  - quality
  - security
  - push
  - notify
  - learn

variables:
  RELEASE_TAG: "1.0.release-${CI_PIPELINE_IID}"
  ...

compile:
  stage: compile
  ...
```

### Dockerfile
```dockerfile
ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/golang:1.21-alpine
...
```
```

### Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `language` | string | Programming language |
| `framework` | string | Framework name |
| `pipeline_id` | string | GitLab pipeline ID |
| `duration` | integer | Execution time (seconds) |
| `stages_count` | integer | Number of stages passed |
| `timestamp` | string | ISO 8601 timestamp |

---

## Best Config Selection

The system selects the "best" configuration based on:

1. **Number of stages passed** (more is better)
2. **Duration** (faster is better, as tiebreaker)

```python
async def get_best_pipeline_config(self, language: str, framework: str) -> Optional[str]:
    """Get the best performing configuration."""
    pipelines = await self.get_successful_pipelines(language, framework, limit=10)

    if not pipelines:
        return None

    # Sort by stages_count (desc) then duration (asc)
    best = max(pipelines, key=lambda p: (p.get('stages_count', 0), -p.get('duration', 9999)))

    # Extract .gitlab-ci.yml from document
    return self._extract_gitlab_ci_from_document(best['document'])
```

---

## Ensuring Learn Stage

All pipelines (including RL-stored ones) are processed to ensure the learn stage exists:

```python
def _ensure_learn_stage(self, pipeline_yaml: str) -> str:
    """
    Ensure the pipeline has the 'learn' stage for RL recording.
    This is added to ALL pipelines (including those from RL storage).
    """
    if '- learn' in pipeline_yaml and 'learn_record:' in pipeline_yaml:
        return pipeline_yaml  # Already has learn stage

    # Add learn stage after notify
    if '- learn' not in pipeline_yaml:
        pipeline_yaml = re.sub(
            r'(- notify)\s*(\n)',
            r'\1\n  - learn  # Reinforcement Learning\2',
            pipeline_yaml
        )

    # Add DEVOPS_BACKEND_URL variable
    if 'DEVOPS_BACKEND_URL' not in pipeline_yaml:
        # ... add variable ...

    # Add learn_record job
    if 'learn_record:' not in pipeline_yaml:
        pipeline_yaml += LEARN_JOB_TEMPLATE

    return pipeline_yaml
```

---

## Monitoring & Debugging

### Check RL Storage Status

```bash
# List all successful pipelines for Go
curl -s "http://localhost:8003/api/v1/pipeline/learn/successful?language=go" | jq .

# Get best config
curl -s "http://localhost:8003/api/v1/pipeline/learn/best?language=go" | jq .config
```

### Backend Logs

```bash
# Watch RL background task
docker logs -f devops-tools-backend 2>&1 | grep "RL"

# Example output:
# [RL Background] Starting pipeline monitor for feature/ai-pipeline-20260203-081701
# [RL Background] Pipeline 215 status: running
# [RL Background] Pipeline 215 status: success
# [RL Background] Pipeline 215 completed with status 'success'. RL result: Pipeline succeeded! Configuration stored for reinforcement learning.
```

### ChromaDB Direct Query

```bash
# List successful_pipelines collection
curl -s "http://localhost:8005/api/v2/tenants/default_tenant/databases/default_database/collections" | jq '.[] | select(.name == "successful_pipelines")'

# Get collection UUID
UUID=$(curl -s "http://localhost:8005/api/v2/tenants/default_tenant/databases/default_database/collections" | jq -r '.[] | select(.name == "successful_pipelines") | .id')

# Query documents
curl -s -X POST "http://localhost:8005/api/v2/tenants/default_tenant/databases/default_database/collections/$UUID/get" \
  -H "Content-Type: application/json" \
  -d '{"include": ["documents", "metadatas"]}' | jq .
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMADB_URL` | `http://chromadb:8000` | ChromaDB server URL |
| `RL_MAX_WAIT_MINUTES` | `15` | Max time to wait for pipeline |
| `RL_CHECK_INTERVAL` | `30` | Seconds between status checks |

### Constants

```python
class PipelineGeneratorService:
    SUCCESSFUL_PIPELINES_COLLECTION = "successful_pipelines"
    TEMPLATES_COLLECTION = "pipeline_templates"
    FEEDBACK_COLLECTION = "pipeline_feedback"
```

---

## Limitations & Future Improvements

### Current Limitations

1. **Single best config**: Only stores/retrieves one "best" config per language/framework
2. **No failure learning**: Failed pipelines are logged but not used for negative learning
3. **No version tracking**: Old configs are overwritten, not versioned

### Future Improvements

1. **A/B Testing**: Store multiple configs and compare performance
2. **Failure Analysis**: Learn from failures to avoid repeating mistakes
3. **User Feedback**: Incorporate manual corrections into RL
4. **Multi-tenant**: Separate RL storage per organization
5. **Confidence Scores**: Track reliability of each config
