# Session Report

**Date**: 2026-05-15  
**Project**: ai-folder  
**Goal**: End-to-end test Java 21 pipeline generation through `deepaksharma.live`, validate LLM and RAG paths, append/reuse Java 21 templates in ChromaDB, and preserve results as a table.

## Summary

Chrome browser testing was performed from `https://deepaksharma.live/pipelines`; no browser navigation used localhost. GitLab RAG and forced LLM flows both produced successful GitLab pipelines, and ChromaDB now contains reusable Java 21 templates for GitLab, Jenkins, and Gitea Actions. Two chat-route issues remain: Jenkins chat missed RAG and Gitea chat returned stale Java 17 content even though direct RAG lookup returns Java 21.

## Pipeline Results

| # | Flow | Source | Public Result | Status | Notes |
|---|------|--------|---------------|--------|-------|
| 1 | GitLab Java 21 Gradle | RAG direct | `https://gitlab.deepaksharma.live/gitlab/mygroup/java21-gradle-sample/-/pipelines/842` | Pass | Used `chromadb-direct`; template `success_java_gradle_be82e08494af`; compile, build, test_image, sast, code_quality, trivy_scan, push_release, notify_success, and learn_record succeeded; notify_failure skipped as expected. |
| 2 | GitLab Java 21 Gradle | Forced LLM | `https://gitlab.deepaksharma.live/gitlab/mygroup/java21-gradle-rag-consumer-clean-20260514-043537/-/pipelines/843` | Pass | Model `Codex Code (gpt-5.5)`; dry-run valid; commit `16b99b5b3a8491bc89251069940aa523db0f1753`; pipeline succeeded. |

## Template Inventory After Testing

| Provider | Collection | Count | Java 21 Templates Verified |
|----------|------------|-------|----------------------------|
| GitLab | `gitlab_successful_template` | 12 | `success_java_gradle_be82e08494af`, `success_java_spring-boot_6c0dba7eb6b7`, `success_java_generic_661eae586040`, `success_java_maven_0baa9dbf0bd2` |
| GitLab | `gitlab_pipeline_templates` | 0 | Not used by the deployed direct-RAG path |
| Jenkins | `jenkins_pipeline_templates` | 2 | Spring Boot, generic |
| Jenkins | `jenkins_successful_pipelines` | 2 | Spring Boot, generic |
| Gitea | `gitea_actions_templates` | 2 | Spring Boot, generic |
| Gitea | `gitea_actions_successful_pipelines` | 2 | Spring Boot, generic |

## Public Browser Test Matrix

| # | Test | URL Origin | Result | Evidence |
|---|------|------------|--------|----------|
| 1 | Load pipeline tool page | `https://deepaksharma.live/pipelines` | Pass | Chrome session remained on public domain. |
| 2 | GitLab provider API | `https://deepaksharma.live/pipelines` | Pass | `/api/v1/pipeline/providers` returned GitLab, Jenkins, and Gitea providers. |
| 3 | GitLab Java 21 Gradle chat flow | `https://deepaksharma.live/pipelines` | Pass | Chat selected RAG, template `success_java_gradle_be82e08494af`, then pipeline `842` succeeded. |
| 4 | GitLab forced LLM flow | Public API | Pass | LLM generation validated and pipeline `843` succeeded. |
| 5 | GitLab Spring Boot RAG lookup | `https://deepaksharma.live/pipelines` | Pass | `learn/best?language=java&framework=spring-boot` returned Java 21 content from reinforcement learning. |
| 6 | GitLab generic RAG lookup | `https://deepaksharma.live/pipelines` | Pass | `learn/best?language=java&framework=generic` returned Java 21 content from reinforcement learning. |
| 7 | GitLab Maven RAG lookup | `https://deepaksharma.live/pipelines` | Pass | `learn/best?language=java&framework=maven` returned Java 21 content from reinforcement learning. |
| 8 | GitLab Gradle Java 21 record | `https://deepaksharma.live/pipelines` | Pass | `learn/successful?language=java&framework=gradle` includes Java 21 record `success_java_gradle_be82e08494af`. |
| 9 | Jenkins Spring Boot RAG lookup | `https://deepaksharma.live/pipelines` | Pass | Direct lookup returned Java 21 Jenkinsfile and Java 21 Dockerfile from `chromadb-successful`. |
| 10 | Jenkins generic RAG lookup | `https://deepaksharma.live/pipelines` | Pass | Direct lookup returned Java 21 Jenkinsfile and Java 21 Dockerfile from `chromadb-successful`. |
| 11 | Gitea Spring Boot RAG lookup | `https://deepaksharma.live/pipelines` | Pass | Direct lookup returned Java 21 workflow and Java 21 Dockerfile from `chromadb-successful`. |
| 12 | Gitea generic RAG lookup | `https://deepaksharma.live/pipelines` | Pass | Direct lookup returned Java 21 workflow and Java 21 Dockerfile from `chromadb-successful`. |
| 13 | Jenkins chat generation | `https://deepaksharma.live/pipelines` | Partial | Chat said no RAG template and generated Java 17 content; direct RAG lookup is correct. |
| 14 | Gitea chat generation | `https://deepaksharma.live/pipelines` | Partial | Chat said a RAG template exists but returned Java 17 image content; direct RAG lookup is correct. |

## Files Changed

| File | Action |
|------|--------|
| `.Codex/task-log/CURRENT.md` | Created session task log |
| `.Codex/task-log/SUMMARY.md` | Created project task summary |
| `.Codex/reports/session-java21-rag-e2e-20260515.md` | Created Markdown report |
| `.Codex/reports/session-java21-rag-e2e-20260515.json` | Created JSON report |
| `.Codex/reports/session-java21-rag-e2e-20260515.html` | Created HTML report |
| `output/playwright/java21-rag-e2e-summary.png` | Created browser screenshot |

## Errors And Resolutions

| Error | Resolution | Impact |
|-------|------------|--------|
| Playwright screenshot command treated filename as selector | Re-ran with `--filename output/playwright/java21-rag-e2e-summary.png --full-page` | Screenshot captured successfully. |
| WSL Docker socket unavailable | Used Windows Docker CLI `docker.exe` | Container and ChromaDB inspection succeeded. |
| GitLab manual template records were not reused | Seeded GitLab Java 21 Spring Boot, generic, and Maven templates as reusable `success_` records with Java 21 metadata | Public `learn/best` now returns Java 21 for those GitLab variants. |

## Next Steps

- Fix Jenkins chat RAG selection so it uses `jenkins_successful_pipelines` before falling back to LLM.
- Fix Gitea chat route so its RAG path uses the Java 21 `learn/best` result instead of stale Java 17 content.
- Add version-aware filtering to GitLab `learn/best` so versionless calls do not pick Java 17 when the request is explicitly Java 21.

## Artifacts

| Artifact | Path |
|----------|------|
| Screenshot | `output/playwright/java21-rag-e2e-summary.png` |
| HTML report | `.Codex/reports/session-java21-rag-e2e-20260515.html` |
| JSON report | `.Codex/reports/session-java21-rag-e2e-20260515.json` |
