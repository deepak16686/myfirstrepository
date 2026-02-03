# Sequence & Flow Diagrams

This document contains detailed diagrams for the DevOps Tools Backend system.

---

## 1. Pipeline Generation Workflow

### Sequence Diagram (Full Workflow)

```mermaid
sequenceDiagram
    participant User
    participant Backend as DevOps Backend
    participant GitLab
    participant ChromaDB
    participant Ollama as Ollama LLM
    participant Runner as GitLab Runner

    User->>Backend: POST /pipeline/workflow
    Note over User,Backend: {repo_url, gitlab_token, auto_commit: true}

    %% Step 1: Repository Analysis
    Backend->>GitLab: GET /projects/:id/repository/tree
    GitLab-->>Backend: File list
    Backend->>GitLab: GET /projects/:id/repository/files/:path
    GitLab-->>Backend: File contents (go.mod, main.go, etc.)
    Note over Backend: Detect language: Go<br/>Framework: generic

    %% Step 2: Template Retrieval (RAG)
    Backend->>ChromaDB: Query successful_pipelines (language=go)
    alt RL Config Found
        ChromaDB-->>Backend: Best successful config
        Note over Backend: Priority 1: Use RL config
    else No RL Config
        Backend->>ChromaDB: Query pipeline_templates (language=go)
        alt Template Found
            ChromaDB-->>Backend: Template document
            Note over Backend: Priority 2-3: Use template
        else No Template
            Note over Backend: Priority 4: Use built-in default
        end
    end

    %% Step 3: Generation (if not template-only)
    alt use_template_only = false
        Backend->>Ollama: Generate pipeline
        Ollama-->>Backend: Generated YAML
        Note over Backend: Validate & fix pipeline
    end

    %% Step 4: Ensure Learn Stage
    Note over Backend: Add "learn" stage if missing<br/>Add DEVOPS_BACKEND_URL<br/>Add learn_record job

    %% Step 5: Commit to GitLab
    Backend->>GitLab: POST /repository/branches (create)
    GitLab-->>Backend: Branch created
    Backend->>GitLab: POST /repository/commits
    Note over Backend: Commit .gitlab-ci.yml + Dockerfile
    GitLab-->>Backend: Commit ID

    %% Step 6: Response to User
    Backend-->>User: Success response with commit info

    %% Step 7: Background RL Monitoring
    Note over Backend: Start background task
    loop Every 30 seconds (max 15 min)
        Backend->>GitLab: GET /pipelines?ref=branch
        GitLab-->>Backend: Pipeline status
        alt Pipeline Complete
            Backend->>GitLab: GET /pipelines/:id/jobs
            GitLab-->>Backend: Job details
            Backend->>ChromaDB: Store successful config
            Note over Backend: RL Learning Complete
        end
    end

    %% Step 8: GitLab CI Execution
    GitLab->>Runner: Trigger pipeline
    Note over Runner: Execute 9 stages:<br/>compile→build→test→sast→<br/>quality→security→push→<br/>notify→learn
    Runner-->>GitLab: Pipeline success
```

---

## 2. Pipeline Execution Flow

### 9-Stage Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           GITLAB CI/CD PIPELINE                                  │
│                              (9 Stages)                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ COMPILE  │───►│  BUILD   │───►│   TEST   │───►│   SAST   │───►│ QUALITY  │
│          │    │          │    │          │    │          │    │          │
│ Build    │    │ Kaniko   │    │ Run unit │    │ Static   │    │ SonarQube│
│ artifact │    │ Docker   │    │ tests    │    │ analysis │    │ scan     │
│ (binary) │    │ image    │    │          │    │ (go vet) │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                                      │
                                                                      ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  LEARN   │◄───│  NOTIFY  │◄───│   PUSH   │◄───│ SECURITY │◄───│          │
│          │    │          │    │          │    │          │    │          │
│ Record   │    │ Splunk   │    │ Tag &    │    │ Trivy    │    │          │
│ success  │    │ HEC      │    │ push     │    │ scan     │    │          │
│ for RL   │    │ notify   │    │ release  │    │ image    │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### Detailed Stage Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: COMPILE                                                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: golang:1.21-alpine                                                       │
│ Script:                                                                         │
│   - go mod download                                                             │
│   - go build -o app .                                                           │
│ Artifacts: app (binary)                                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: BUILD                                                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: kaniko-executor:debug                                                    │
│ Dependencies: compile (artifact)                                                │
│ Script:                                                                         │
│   - Create /kaniko/.docker/config.json                                          │
│   - /kaniko/executor \                                                          │
│       --destination ai-nexus:5001/apm-repo/demo/${IMAGE_NAME}:${IMAGE_TAG}     │
│       --build-arg BASE_REGISTRY=ai-nexus:5001                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: TEST                                                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: golang:1.21-alpine                                                       │
│ Script:                                                                         │
│   - go test ./... -v || true                                                    │
│ Allow Failure: true                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 4: SAST (Static Application Security Testing)                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: golang:1.21-alpine                                                       │
│ Script:                                                                         │
│   - go vet ./... || true                                                        │
│ Allow Failure: true                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 5: QUALITY                                                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: sonarsource-sonar-scanner-cli:latest                                     │
│ Script:                                                                         │
│   - sonar-scanner \                                                             │
│       -Dsonar.projectKey=${CI_PROJECT_NAME} \                                  │
│       -Dsonar.host.url=http://ai-sonarqube:9000 \                              │
│       -Dsonar.token=${SONAR_TOKEN}                                             │
│ Allow Failure: true                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 6: SECURITY                                                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: curlimages-curl:latest                                                   │
│ Services:                                                                       │
│   - aquasec-trivy:latest (alias: trivy-server)                                 │
│     Command: /usr/local/bin/trivy server --listen 0.0.0.0:8083                 │
│ Script:                                                                         │
│   - sleep 10  # Wait for Trivy server                                          │
│   - curl -s "http://trivy-server:8083/healthz"                                 │
│ Allow Failure: true                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 7: PUSH                                                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: kaniko-executor:debug                                                    │
│ Script:                                                                         │
│   - /kaniko/executor \                                                          │
│       --destination ai-nexus:5001/apm-repo/demo/${IMAGE_NAME}:${RELEASE_TAG}   │
│ Note: Creates release-tagged image                                              │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 8: NOTIFY                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Jobs:                                                                           │
│   notify_success (when: on_success):                                           │
│     - curl Splunk HEC: "Pipeline succeeded"                                     │
│   notify_failure (when: on_failure):                                           │
│     - curl Splunk HEC: "Pipeline failed"                                        │
│ Allow Failure: true                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STAGE 9: LEARN (Reinforcement Learning)                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Image: curlimages-curl:latest                                                   │
│ When: on_success                                                                │
│ Script:                                                                         │
│   - echo "REINFORCEMENT LEARNING - Recording Success"                           │
│   - echo "Pipeline ${CI_PIPELINE_ID} completed successfully!"                   │
│   - echo "This configuration will be stored for future AI pipeline generation" │
│   - echo "RL Status - Backend background task is recording this success"        │
│ Allow Failure: true                                                             │
│                                                                                 │
│ Note: Actual RL storage is done by backend background task                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Reinforcement Learning Flow

### RL Data Flow

```mermaid
flowchart TB
    subgraph Pipeline["GitLab Pipeline Execution"]
        P1[compile] --> P2[build]
        P2 --> P3[test]
        P3 --> P4[sast]
        P4 --> P5[quality]
        P5 --> P6[security]
        P6 --> P7[push]
        P7 --> P8[notify]
        P8 --> P9[learn]
    end

    subgraph Backend["DevOps Backend"]
        BG[Background Monitor Task]
        RL[RL Storage Logic]
    end

    subgraph ChromaDB["ChromaDB"]
        SP[(successful_pipelines)]
        PT[(pipeline_templates)]
    end

    P9 -->|Display RL message| User([User sees learn stage])
    BG -->|Check every 30s| Pipeline
    Pipeline -->|Status: success| BG
    BG -->|Record result| RL
    RL -->|Store config| SP

    subgraph Future["Future Pipeline Generation"]
        FG[Generate Pipeline]
        FG -->|Priority 1| SP
        FG -->|Priority 2-3| PT
    end
```

### RL Priority Selection

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    TEMPLATE SELECTION PRIORITY                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────┐
                         │ Get Reference       │
                         │ Pipeline            │
                         │ (language, framework)│
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │ Priority 1: Check RL Storage  │
                    │ (successful_pipelines)        │
                    │                               │
                    │ Query: language=X, framework=Y│
                    └───────────────┬───────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                    Found?                Not Found
                         │                     │
                         ▼                     ▼
              ┌─────────────────┐   ┌─────────────────────┐
              │ Return RL       │   │ Priority 2: Check   │
              │ Config          │   │ Templates           │
              │ (proven to work)│   │ (language+framework)│
              └─────────────────┘   └──────────┬──────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │                     │
                               Found?                Not Found
                                    │                     │
                                    ▼                     ▼
                         ┌─────────────────┐   ┌─────────────────────┐
                         │ Return Template │   │ Priority 3: Check   │
                         │                 │   │ Language-only       │
                         └─────────────────┘   └──────────┬──────────┘
                                                          │
                                               ┌──────────┴──────────┐
                                               │                     │
                                          Found?                Not Found
                                               │                     │
                                               ▼                     ▼
                                    ┌─────────────────┐   ┌─────────────────┐
                                    │ Return Template │   │ Priority 4:     │
                                    │                 │   │ Built-in Default│
                                    └─────────────────┘   └─────────────────┘
```

---

## 4. Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         COMPONENT INTERACTIONS                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

     ┌─────────────┐
     │   CLIENT    │
     │  (curl/UI)  │
     └──────┬──────┘
            │ HTTP
            ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                           DEVOPS TOOLS BACKEND                                 │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                         FASTAPI APPLICATION                              │  │
│  │                                                                          │  │
│  │  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐        │  │
│  │  │ Pipeline Router│    │  Chat Router   │    │ Health Router  │        │  │
│  │  │ /api/v1/pipeline│    │ /api/v1/chat  │    │    /health     │        │  │
│  │  └───────┬────────┘    └───────┬────────┘    └────────────────┘        │  │
│  │          │                     │                                        │  │
│  │          └──────────┬──────────┘                                        │  │
│  │                     │                                                   │  │
│  │                     ▼                                                   │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │  │
│  │  │              PIPELINE GENERATOR SERVICE                           │  │  │
│  │  │                                                                   │  │  │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │  │  │
│  │  │  │ analyze_repo │  │ generate_    │  │ commit_to_   │            │  │  │
│  │  │  │              │  │ pipeline     │  │ gitlab       │            │  │  │
│  │  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │  │  │
│  │  │         │                 │                 │                     │  │  │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │  │  │
│  │  │  │ get_reference│  │ validate_    │  │ record_      │            │  │  │
│  │  │  │ _pipeline    │  │ pipeline     │  │ pipeline_    │            │  │  │
│  │  │  │ (RAG)        │  │              │  │ result (RL)  │            │  │  │
│  │  │  └──────┬───────┘  └──────────────┘  └──────┬───────┘            │  │  │
│  │  └─────────┼──────────────────────────────────┼─────────────────────┘  │  │
│  │            │                                  │                        │  │
│  └────────────┼──────────────────────────────────┼────────────────────────┘  │
│               │                                  │                           │
└───────────────┼──────────────────────────────────┼───────────────────────────┘
                │                                  │
    ┌───────────┼───────────┬──────────────────────┼───────────┐
    │           │           │                      │           │
    ▼           ▼           ▼                      ▼           ▼
┌───────┐  ┌───────┐  ┌─────────┐            ┌─────────┐  ┌───────┐
│GitLab │  │ChromaDB│  │ Ollama  │            │ Nexus   │  │SonarQ │
│       │  │ (RAG)  │  │  (LLM)  │            │Registry │  │ ube   │
│:8929  │  │ :8005  │  │ :11434  │            │ :5001   │  │ :9000 │
└───────┘  └───────┘  └─────────┘            └─────────┘  └───────┘
```

---

## 5. Error Handling Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ERROR HANDLING FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────┐
                         │ Pipeline Generation │
                         │ Request             │
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │ Try: Get Reference Pipeline   │
                    │ from RL/ChromaDB              │
                    └───────────────┬───────────────┘
                                    │
                         ┌──────────┴──────────┐
                    Success                 Failure
                         │                     │
                         │                     ▼
                         │          ┌─────────────────────┐
                         │          │ Fallback: Built-in  │
                         │          │ Default Template    │
                         │          └──────────┬──────────┘
                         │                     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │ Try: Generate with Ollama LLM │
                    └───────────────┬───────────────┘
                                    │
                         ┌──────────┴──────────┐
                    Success                 Failure
                         │                     │
                         ▼                     ▼
              ┌─────────────────┐   ┌─────────────────────┐
              │ Validate &      │   │ Fallback: Use       │
              │ Fix Pipeline    │   │ Default Template    │
              └────────┬────────┘   └──────────┬──────────┘
                       │                       │
                       └───────────┬───────────┘
                                   │
                                   ▼
                    ┌───────────────────────────────┐
                    │ Ensure Learn Stage Present    │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │ Try: Commit to GitLab         │
                    └───────────────┬───────────────┘
                                    │
                         ┌──────────┴──────────┐
                    Success                 Failure
                         │                     │
                         ▼                     ▼
              ┌─────────────────┐   ┌─────────────────────┐
              │ Return Success  │   │ Return Error        │
              │ + Start RL      │   │ Response            │
              │ Monitor         │   │ (HTTP 500)          │
              └─────────────────┘   └─────────────────────┘
```

---

## 6. Mermaid Diagrams (Copy-Paste Ready)

### Pipeline Generation Sequence

```mermaid
sequenceDiagram
    participant U as User
    participant B as Backend
    participant G as GitLab
    participant C as ChromaDB
    participant R as Runner

    U->>B: POST /workflow
    B->>G: Analyze repo
    G-->>B: Files & structure
    B->>C: Get RL/template
    C-->>B: Pipeline config
    B->>G: Commit files
    G-->>B: Commit ID
    B-->>U: Success response

    Note over B,R: Background RL monitoring
    G->>R: Trigger pipeline
    R-->>G: Pipeline success
    B->>C: Store for RL
```

### RL Flow

```mermaid
flowchart LR
    subgraph Generation
        A[Request] --> B{RL Config?}
        B -->|Yes| C[Use RL]
        B -->|No| D{Template?}
        D -->|Yes| E[Use Template]
        D -->|No| F[Use Default]
    end

    subgraph Execution
        G[Pipeline Runs] --> H{Success?}
        H -->|Yes| I[Store in RL]
        H -->|No| J[Log Failure]
    end

    C --> G
    E --> G
    F --> G
    I --> B
```

---

## Viewing Mermaid Diagrams

1. **VS Code**: Install "Markdown Preview Mermaid Support" extension
2. **GitLab**: Native support in markdown files
3. **Online**: Use [Mermaid Live Editor](https://mermaid.live/)
4. **Export**: Convert to PNG/SVG using mermaid-cli
