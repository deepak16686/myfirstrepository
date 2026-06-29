# Session Report
**Date**: 2026-05-18
**Project**: ai-folder
**Goal**: Create accurate Figma/FigJam diagrams for the GitLab, Jenkins, and GitHub pipeline generator architecture, infrastructure, request flow, data flow, learning loops, and file responsibilities.

## Summary
Created six FigJam diagrams from the live repository implementation under `dev-stack/backend`. Native FigJam table creation was blocked by Figma reauthentication, so the file-responsibility table is represented as a FigJam diagram and as a Markdown table in the final response.

## Figma Outputs
| Diagram | URL |
|---|---|
| Component Architecture | https://www.figma.com/online-whiteboard/create-diagram/a0d731e1-b969-407c-9031-a958b459916c |
| Infrastructure Runtime | https://www.figma.com/online-whiteboard/create-diagram/24e63781-d88d-473f-aedc-506d71878870 |
| Request Sequence | https://www.figma.com/online-whiteboard/create-diagram/36288c4f-a634-4261-a512-78643c59d0b0 |
| Data Flow and Learning Loops | https://www.figma.com/online-whiteboard/create-diagram/e662a1ce-1023-40cc-80b3-5c2babb5022e |
| Provider Stage Matrix | https://www.figma.com/online-whiteboard/create-diagram/938bae0d-3ccf-44a1-9ee9-b7c4466ad6f6 |
| File Responsibility Map | https://www.figma.com/online-whiteboard/create-diagram/e2a505bc-aed0-48ba-83fb-ffffcb9ae423 |

## Source Files Reviewed
| File | Responsibility |
|---|---|
| `dev-stack/backend/app/main.py` | FastAPI composition root and router registration |
| `dev-stack/backend/app/config.py` | Tool URLs, Vault secret overlay, LLM/provider settings |
| `dev-stack/backend/app/routers/pipeline.py` | GitLab workflow, commit, monitoring, learning, self-healing endpoints |
| `dev-stack/backend/app/routers/jenkins_pipeline.py` | Jenkins chat/workflow/commit/build/RL endpoints |
| `dev-stack/backend/app/routers/github_pipeline.py` | GitHub/Gitea Actions chat/workflow/commit/RL endpoints |
| `dev-stack/backend/app/services/pipeline/generator.py` | GitLab pipeline generation facade and RAG/LLM orchestration |
| `dev-stack/backend/app/services/jenkins_pipeline/generator.py` | Jenkinsfile generation facade and validation loop |
| `dev-stack/backend/app/services/github_pipeline/generator.py` | GitHub Actions workflow generation facade |
| `dev-stack/backend/app/services/pipeline/templates.py` | GitLab ChromaDB template lookup and storage |
| `dev-stack/backend/app/services/*/learning.py` | Provider-specific feedback and successful pipeline storage |
| `dev-stack/backend/app/services/self_healing_workflow.py` | GitLab self-healing monitor and fix loop |
| `dev-stack/backend/app/services/*llm_fixer.py` | LLM repair prompts and iterative validation fixes |
| `dev-stack/backend/app/integrations/chromadb.py` | ChromaDB v2 REST client |
| `dev-stack/backend/app/integrations/llm_provider.py` | Active LLM provider factory |
| `dev-stack/backend/app/services/shared/deep_analyzer.py` | Deep repo analysis and image resolution |
| `dev-stack/backend/app/prompts/pipeline_system_prompt.txt` | GitLab LLM prompt rules |
| `dev-stack/backend/app/prompts/jenkins_system_prompt.txt` | Jenkins LLM prompt rules |

## Accuracy Notes
- Current GitLab self-healing code uses `max_attempts=10`; Jenkins and GitHub validation paths also default to iterative LLM fixing with max attempts commonly set to 10 in router calls.
- The 9 count in the implementation refers to the provider stage/job model: GitLab stages include compile, build, test, sast, quality, security, push, notify, learn; Jenkins and GitHub mirror this as named stages/jobs.
- GitHub in this codebase targets Gitea Actions as a self-hosted GitHub Actions compatible runtime.

## Blockers
| Blocker | Impact |
|---|---|
| Figma `whoami` returned `UNAUTHORIZED` reauthentication required | Could not create a native FigJam table node with `use_figma`; generated the file-responsibility map as a diagram instead |
