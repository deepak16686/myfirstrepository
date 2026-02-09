# DevOps Tools Backend - Sequential Flow Reference

## Complete Request Flow (Step-by-Step)

### Phase 1: User Initiates Pipeline Generation

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 1 | **User** | Web Portal UI | Pastes repo URL + configures settings | HTTP POST request |
| 2 | **API Router** | `app/routers/pipeline.py:544` | Receives `/api/v1/pipeline/workflow` request | Route to handler |
| 3 | **Request Validation** | `app/models/pipeline_schemas.py` | Validates `PipelineWorkflowRequest` schema | Validated data |

---

### Phase 2: Repository Analysis

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 4 | **Pipeline Generator** | `app/services/pipeline/pipeline_generator.py:50` | Calls `generate_pipeline()` | Orchestration starts |
| 5 | **Repo Analyzer** | `app/services/pipeline/repo_analyzer.py:30` | Clones repo, scans files | `{"language": "ruby", "framework": "sinatra", "dependencies": [...]}` |
| 6 | **Language Detection** | `repo_analyzer.py:detect_language()` | Checks file extensions, package manifests | Detected language |
| 7 | **Framework Detection** | `repo_analyzer.py:detect_framework()` | Scans Gemfile, package.json, etc. | Detected framework |

---

### Phase 3: RAG Template Lookup (ChromaDB)

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 8 | **Template Manager** | `app/services/pipeline/templates.py:120` | Calls `get_best_template_files(language, framework)` | Query ChromaDB |
| 9 | **ChromaDB Client** | `app/integrations/chromadb.py:85` | Queries collections: `successful_pipelines`, `pipeline_templates` | Vector search results |
| 10 | **Template Ranking** | `templates.py:filter_templates()` | Prioritizes `manual_` templates, sorts by `stages_count` | Best template or None |

---

### Phase 4: Decision Point - RAG vs LLM

| Scenario | Condition | File Reference | Next Step | Commit Tag |
|----------|-----------|----------------|-----------|------------|
| **Path A: chromadb-direct** | RAG has BOTH `.gitlab-ci.yml` AND `Dockerfile` | `templates.py:145` | → Skip to Phase 6 (Image Seeding) | `[RAG Template]` |
| **Path B: chromadb-reference** | RAG has partial template (only one file) | `templates.py:150` | → Phase 5 (LLM adapts template) | `[RAG + LLM]` |
| **Path C: LLM from scratch** | No RAG template found | `templates.py:155` | → Phase 5 (LLM generates everything) | `[AI Generated]` |

---

### Phase 5: LLM Generation (if needed)

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 11 | **LLM Provider Factory** | `app/integrations/llm_provider.py:15` | Checks `LLM_PROVIDER` env var | Selects Ollama or Claude |
| 12a | **Ollama Client** (if `LLM_PROVIDER=ollama`) | `app/integrations/ollama_client.py:35` | Calls `http://localhost:11434/api/chat` with `pipeline-generator-v5` model | Generated YAML + Dockerfile |
| 12b | **Claude CLI** (if `LLM_PROVIDER=claude-code`) | `app/integrations/claude_client.py:45` | Executes `npx @anthropic-ai/claude-code` in Docker | Generated YAML + Dockerfile |
| 13 | **System Prompt** | `app/prompts/pipeline_system_prompt.txt` | Loaded into LLM context | Instructions for 9-stage pipeline |
| 14 | **LLM Response** | LLM output | Parses JSON response | `.gitlab-ci.yml` + `Dockerfile` content |

---

### Phase 6: Docker Image Seeding

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 15 | **Image Seeder** | `app/services/pipeline/image_seeder.py:40` | Extracts image refs from YAML + Dockerfile | List of required images |
| 16 | **Nexus Check** | `image_seeder.py:check_image_exists()` | Queries `http://localhost:5001/v2/{repo}/manifests/{tag}` | Exists: True/False |
| 17 | **Skopeo Copy** | `image_seeder.py:seed_image()` | `skopeo copy docker://{source} docker://localhost:5001/{dest}` | Image copied to Nexus |
| 18 | **Pre-built Images** | Pre-seeded in Nexus | Uses `ruby:3.2-alpine-build`, etc. (avoids `apk add` in DinD) | No network calls in runner |

---

### Phase 7: GitLab Commit

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 19 | **Branch Creation** | `pipeline.py:612` | Generates branch name: `feature/ai-pipeline-{timestamp}` | Branch name |
| 20 | **Commit Message** | `pipeline.py:619-626` | Determines tag based on `model_used`: `[RAG Template]` / `[RAG + LLM]` / `[AI Generated]` | Commit message |
| 21 | **GitLab Client** | `app/integrations/gitlab.py:55` | `POST /api/v4/projects/{id}/repository/commits` with files | Commit SHA |
| 22 | **Response** | `pipeline.py:627-632` | Returns commit details: `branch`, `commit_id`, `web_url`, `project_id` | JSON response to user |

---

### Phase 8: Pipeline Monitoring (Background Task)

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 23 | **Background Task** | `pipeline.py:634` | Launches `monitor_pipeline_for_learning()` async | Runs in background |
| 24 | **GitLab Polling** | `pipeline.py:wait_for_pipeline()` | `GET /api/v4/projects/{id}/pipelines` every 30 seconds | Pipeline status |
| 25 | **Job Status Check** | `gitlab.py:get_pipeline_jobs()` | `GET /api/v4/projects/{id}/pipelines/{pipeline_id}/jobs` | All 10 job statuses |
| 26 | **Wait Loop** | Max 15 minutes (30 checks) | Polls until `status in ['success', 'failed', 'canceled']` | Final status |

---

### Phase 9: Failure Detection & Self-Healing

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 27 | **Failure Detected** | `pipeline.py:check_pipeline_status()` | Any job failed (status != 'success') | Trigger self-heal |
| 28 | **LLM Fixer** | `app/services/llm_fixer.py:95` | `analyze_and_fix_pipeline()` | Error classification |
| 29 | **Error Classification** | `llm_fixer.py:ERROR_PATTERNS` | Regex matching on job logs | Error type (tls_network_error, image_not_found, etc.) |
| 30 | **Fix Generation** | `llm_fixer.py:_build_fix_prompt()` | Sends logs + error type to LLM | Suggested fixes |
| 31 | **Fix Commit** | `gitlab.py:commit_to_gitlab()` | Creates new commit with fixed files | New commit SHA |
| 32 | **Retry Pipeline** | GitLab webhook trigger | New commit auto-triggers pipeline | New pipeline ID |
| 33 | **Attempt Counter** | `llm_fixer.py:attempt_count` | Increments (max 10 attempts) | Continue or stop |
| 34 | **Loop** | Repeat steps 24-33 | Until success or max attempts | Final outcome |

---

### Phase 10: Quality Gate & RAG Storage

| Step | Component | File | Action | Output |
|------|-----------|------|--------|--------|
| 35 | **Quality Gate** | `pipeline.py:_check_all_jobs_passed()` | Verifies **ALL 10 jobs passed** (including `allow_failure: true`) | Pass/Fail |
| 36 | **RAG Storage** | `app/services/pipeline/templates.py:200` | `store_manual_template(language, framework, gitlab_ci, dockerfile)` | Store in ChromaDB |
| 37 | **Content Hash** | `templates.py:calculate_hash()` | SHA256 of YAML + Dockerfile | Unique hash |
| 38 | **Template ID** | Format: `manual_{language}_{framework}_{hash[:12]}` | Example: `manual_ruby_sinatra_a1b2c3d4e5f6` | Template ID |
| 39 | **ChromaDB Insert** | `chromadb.py:add_documents()` | Insert into `successful_pipelines` collection | Stored for future reuse |

---

## File Dependency Map

### When User Pastes Repo URL → Files Loaded in Order

```
1. app/routers/pipeline.py                        # Entry point
2. app/models/pipeline_schemas.py                 # Request validation
3. app/services/pipeline/pipeline_generator.py    # Main orchestrator
4. app/services/pipeline/repo_analyzer.py         # Repo analysis
5. app/services/pipeline/templates.py             # RAG lookup
6. app/integrations/chromadb.py                   # ChromaDB client
   └─ (if RAG found) → Return template directly
   └─ (if no RAG) → Continue to LLM

7. app/integrations/llm_provider.py               # LLM factory
   ├─ app/integrations/ollama_client.py           # Ollama path
   └─ app/integrations/claude_client.py           # Claude path

8. app/prompts/pipeline_system_prompt.txt         # LLM system prompt
9. app/services/pipeline/image_seeder.py          # Docker image seeding
10. app/integrations/gitlab.py                    # GitLab commit

# Background monitoring (runs async):
11. app/services/llm_fixer.py                     # Self-healing orchestrator
12. app/services/pipeline/self_healing.py         # Workflow state machine
```

---

## Key Decision Points (Conditionals in Code)

### 1. RAG vs LLM Decision
**File:** `app/services/pipeline/templates.py:145-160`
```python
template = get_best_template_files(language, framework)
if template and template.get('gitlab_ci') and template.get('dockerfile'):
    # chromadb-direct → Skip LLM
    return template, 'chromadb-direct'
elif template and (template.get('gitlab_ci') or template.get('dockerfile')):
    # chromadb-reference → LLM adapts
    return llm_generate_with_reference(template), 'chromadb-reference'
else:
    # No template → LLM from scratch
    return llm_generate_from_scratch(), 'llm-generated'
```

### 2. LLM Provider Selection
**File:** `app/integrations/llm_provider.py:20-35`
```python
provider = os.getenv('LLM_PROVIDER', 'ollama')
if provider == 'claude-code':
    return ClaudeClient()
else:
    return OllamaClient()
```

### 3. Self-Healing Max Attempts
**File:** `app/services/llm_fixer.py:110-125`
```python
MAX_ATTEMPTS = 10
if attempt_count >= MAX_ATTEMPTS:
    return {'status': 'max_attempts_reached', 'message': 'Self-healing exhausted'}
```

### 4. Quality Gate for RAG Save
**File:** `app/routers/pipeline.py:_check_all_jobs_passed()`
```python
for job in jobs:
    if job['status'] != 'success':
        return False  # Don't save broken templates
return True  # All jobs passed → Save to RAG
```

---

## Environment Variables Impact

| Env Var | Default | Impact | File Reference |
|---------|---------|--------|----------------|
| `LLM_PROVIDER` | `ollama` | Selects Ollama or Claude Code CLI | `llm_provider.py:20` |
| `OLLAMA_MODEL` | `pipeline-generator-v5` | Model for Ollama generation | `ollama_client.py:40` |
| `GITLAB_URL` | `http://gitlab-server` | GitLab API endpoint | `gitlab.py:25` |
| `NEXUS_REGISTRY` | `ai-nexus:5001` | Docker registry for image seeding | `image_seeder.py:30` |
| `CHROMADB_HOST` | `chromadb` | ChromaDB service hostname | `chromadb.py:20` |
| `MAX_SELF_HEAL_ATTEMPTS` | `10` | Self-healing retry limit | `llm_fixer.py:15` |

---

## Pipeline Stages (Generated)

All pipelines have **9 stages** (defined in system prompt):

1. **compile** - Compile source code, install dependencies
2. **build** - Build Docker image using Kaniko
3. **test** - Run unit tests inside built image
4. **sast** - Static analysis (Brakeman/Semgrep)
5. **quality** - Code quality (RuboCop/ESLint)
6. **security** - Trivy container scanning
7. **push** - Push image to Nexus
8. **notify** - Send notifications (success/failure)
9. **learn** - Record pipeline to ChromaDB

---

## Error Classification Patterns

**File:** `app/services/llm_fixer.py:ERROR_PATTERNS`

| Pattern Regex | Error Type | Fix Strategy |
|---------------|------------|--------------|
| `manifest unknown\|MANIFEST_UNKNOWN` | `image_not_found` | Seed missing image to Nexus |
| `tls.*error\|ssl.*error\|unable to select packages` | `tls_network_error` | Use pre-built images (no `apk add`) |
| `connection refused\|cannot connect` | `service_connection` | Check service availability |
| `command not found\|no such file` | `missing_command` | Install missing tool |
| `compilation failed\|build failed` | `build_failure` | Fix source code errors |
| `permission denied\|access denied` | `permission_error` | Fix file/registry permissions |
| `timed out\|execution expired\|deadline exceeded` | `timeout_error` | Increase timeout or optimize |
| `artifact.*not found\|no artifacts` | `artifact_missing` | Fix artifact paths |
| `yaml.*error\|syntax error` | `yaml_syntax` | Fix YAML formatting |
| `invalid.*stage\|unknown stage` | `invalid_stage` | Fix stage names |

---

## Success Criteria

### Pipeline Generation Success
✅ Generated `.gitlab-ci.yml` + `Dockerfile`
✅ Files committed to GitLab
✅ Pipeline triggered
✅ Monitoring task started

### Self-Healing Success
✅ All 10 jobs passed (including `allow_failure: true`)
✅ Template stored in ChromaDB
✅ Available for future RAG reuse

### Failure Conditions
❌ Max 10 self-healing attempts exhausted
❌ LLM fails to generate valid YAML
❌ GitLab API errors
❌ ChromaDB connection failures

---

**Last Updated:** 2026-02-09
**System Version:** v5 (qwen3:32b base, Claude Code CLI support)
