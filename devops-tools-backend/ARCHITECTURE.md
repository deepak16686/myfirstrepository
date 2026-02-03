# AI DevOps Pipeline Generator - Architecture

## Overview
A custom web application for generating CI/CD pipelines using AI with RAG (Retrieval Augmented Generation).

## Flow
```
User -> Frontend -> Chat API -> LLM (Ollama) -> Tool Calls -> Pipeline API -> GitLab
                                    |
                                    v
                              ChromaDB (RAG)
                              (Pipeline Templates)
```

## Components

### 1. Frontend (React/Vite)
- Simple chat interface
- Pipeline preview with syntax highlighting
- Approval workflow (Yes/No buttons)
- Pipeline status display

### 2. Chat Service (FastAPI - integrated into devops-tools-backend)
- Conversation management
- LLM orchestration with tool calling
- Session management
- Conversation history storage

### 3. Pipeline Service (existing)
- Repository analysis
- Pipeline generation using RAG
- Commit to GitLab
- Pipeline status monitoring

### 4. Ollama (LLM)
- llama3.1:8b model
- Native tool/function calling
- Streaming responses

### 5. ChromaDB (Vector DB)
- Pipeline templates storage
- Semantic search for RAG

### 6. PostgreSQL (Database)
- Conversation history
- Generated pipelines
- User sessions

## API Endpoints

### Chat API
- `POST /api/v1/chat` - Send message, get AI response
- `GET /api/v1/chat/history/{session_id}` - Get conversation history
- `POST /api/v1/chat/approve/{session_id}` - Approve pipeline commit

### Pipeline API (existing)
- `POST /api/v1/pipeline/generate` - Generate pipeline
- `POST /api/v1/pipeline/commit` - Commit to GitLab
- `POST /api/v1/pipeline/status` - Check pipeline status

## Tool Definitions for LLM

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "generate_pipeline",
        "description": "Generate CI/CD pipeline for a GitLab repository",
        "parameters": {
          "type": "object",
          "properties": {
            "repo_url": {
              "type": "string",
              "description": "GitLab repository URL"
            }
          },
          "required": ["repo_url"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "commit_pipeline",
        "description": "Commit generated pipeline to GitLab repository",
        "parameters": {
          "type": "object",
          "properties": {
            "repo_url": {
              "type": "string",
              "description": "GitLab repository URL"
            }
          },
          "required": ["repo_url"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "check_pipeline_status",
        "description": "Check GitLab CI/CD pipeline status",
        "parameters": {
          "type": "object",
          "properties": {
            "repo_url": {
              "type": "string",
              "description": "GitLab repository URL"
            },
            "branch": {
              "type": "string",
              "description": "Branch name"
            }
          },
          "required": ["repo_url", "branch"]
        }
      }
    }
  ]
}
```

## Database Schema

```sql
-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    role VARCHAR(20), -- 'user', 'assistant', 'tool'
    content TEXT,
    tool_calls JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Generated Pipelines
CREATE TABLE pipelines (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    repo_url TEXT,
    dockerfile TEXT,
    gitlab_ci TEXT,
    status VARCHAR(20), -- 'generated', 'approved', 'committed'
    commit_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Directory Structure

```
devops-tools-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   ├── schemas.py
│   │   └── database.py
│   ├── routers/
│   │   ├── pipeline.py (existing)
│   │   ├── chat.py (new)
│   │   └── health.py
│   ├── services/
│   │   ├── pipeline_service.py (existing)
│   │   ├── chat_service.py (new)
│   │   └── llm_service.py (new)
│   └── integrations/
│       ├── ollama.py (existing)
│       ├── gitlab.py (existing)
│       └── chromadb.py (existing)
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── docker-compose.yml
```
