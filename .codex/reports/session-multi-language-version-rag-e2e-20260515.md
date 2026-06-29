# Session Report
**Date**: 2026-05-15
**Project**: ai-folder / devops-tools-backend
**Goal**: Complete browser E2E RAG template validation for Java versions, Python versions, and at least 10 languages through the public deepaksharma.live domain.

## Summary
Chrome E2E validation ran from `https://deepaksharma.live/pipelines` and passed all 363 provider checks. The matrix covers 121 language/version/framework combinations across GitLab, Jenkins, and Gitea, with every lookup returning a version-marked RAG template from ChromaDB.

## Provider Results
| Provider | Passed | Total | Status |
|---|---:|---:|---|
| GitLab | 121 | 121 | PASS |
| Jenkins | 121 | 121 | PASS |
| Gitea | 121 | 121 | PASS |

## Language Results
| Language | Provider Checks Passed | Status |
|---|---:|---|
| java | 60/60 | PASS |
| python | 126/126 | PASS |
| javascript | 27/27 | PASS |
| typescript | 27/27 | PASS |
| go | 27/27 | PASS |
| rust | 12/12 | PASS |
| ruby | 18/18 | PASS |
| php | 18/18 | PASS |
| dotnet | 12/12 | PASS |
| csharp | 12/12 | PASS |
| kotlin | 12/12 | PASS |
| scala | 12/12 | PASS |

## ChromaDB Matrix Records
| Collection | Matrix Records |
|---|---:|
| GitLab successful | 121 |
| Jenkins successful | 121 |
| Jenkins templates | 121 |
| Gitea successful | 121 |
| Gitea templates | 121 |

## Per-Language ChromaDB Records Per Collection
| Language | Records |
|---|---:|
| java | 20 |
| python | 42 |
| javascript | 9 |
| typescript | 9 |
| go | 9 |
| rust | 4 |
| ruby | 6 |
| php | 6 |
| dotnet | 4 |
| csharp | 4 |
| kotlin | 4 |
| scala | 4 |

## Issues Fixed
| Issue | Fix | Verification |
|---|---|---|
| GitLab reusable-template validator rejected version-qualified framework keys such as fastapi-python3.11 and generic-ruby3.2. | Added language-version alias normalization and compatibility matching in pipeline template validation. | GitLab improved from 0/121 to 116/121, then passed 121/121 after the Java generic fix. |
| GitLab java/generic version templates were found but rejected because the generic Java compile gate only accepted Gradle by default. | Allowed Maven, Gradle, and javac compile commands when generic Java does not specify a build tool. | Final public Chrome matrix passed 363/363. |

## Complete Combination Results
| # | Language | Version | Framework | GitLab | Jenkins | Gitea |
|---:|---|---|---|---|---|---|
| 1 | java | 8 | gradle | PASS | PASS | PASS |
| 2 | java | 8 | maven | PASS | PASS | PASS |
| 3 | java | 8 | spring-boot | PASS | PASS | PASS |
| 4 | java | 8 | generic | PASS | PASS | PASS |
| 5 | java | 11 | gradle | PASS | PASS | PASS |
| 6 | java | 11 | maven | PASS | PASS | PASS |
| 7 | java | 11 | spring-boot | PASS | PASS | PASS |
| 8 | java | 11 | generic | PASS | PASS | PASS |
| 9 | java | 17 | gradle | PASS | PASS | PASS |
| 10 | java | 17 | maven | PASS | PASS | PASS |
| 11 | java | 17 | spring-boot | PASS | PASS | PASS |
| 12 | java | 17 | generic | PASS | PASS | PASS |
| 13 | java | 21 | gradle | PASS | PASS | PASS |
| 14 | java | 21 | maven | PASS | PASS | PASS |
| 15 | java | 21 | spring-boot | PASS | PASS | PASS |
| 16 | java | 21 | generic | PASS | PASS | PASS |
| 17 | java | 26 | gradle | PASS | PASS | PASS |
| 18 | java | 26 | maven | PASS | PASS | PASS |
| 19 | java | 26 | spring-boot | PASS | PASS | PASS |
| 20 | java | 26 | generic | PASS | PASS | PASS |
| 21 | python | 3.8 | generic | PASS | PASS | PASS |
| 22 | python | 3.8 | fastapi | PASS | PASS | PASS |
| 23 | python | 3.8 | django | PASS | PASS | PASS |
| 24 | python | 3.8 | flask | PASS | PASS | PASS |
| 25 | python | 3.8 | streamlit | PASS | PASS | PASS |
| 26 | python | 3.8 | celery | PASS | PASS | PASS |
| 27 | python | 3.9 | generic | PASS | PASS | PASS |
| 28 | python | 3.9 | fastapi | PASS | PASS | PASS |
| 29 | python | 3.9 | django | PASS | PASS | PASS |
| 30 | python | 3.9 | flask | PASS | PASS | PASS |
| 31 | python | 3.9 | streamlit | PASS | PASS | PASS |
| 32 | python | 3.9 | celery | PASS | PASS | PASS |
| 33 | python | 3.10 | generic | PASS | PASS | PASS |
| 34 | python | 3.10 | fastapi | PASS | PASS | PASS |
| 35 | python | 3.10 | django | PASS | PASS | PASS |
| 36 | python | 3.10 | flask | PASS | PASS | PASS |
| 37 | python | 3.10 | streamlit | PASS | PASS | PASS |
| 38 | python | 3.10 | celery | PASS | PASS | PASS |
| 39 | python | 3.11 | generic | PASS | PASS | PASS |
| 40 | python | 3.11 | fastapi | PASS | PASS | PASS |
| 41 | python | 3.11 | django | PASS | PASS | PASS |
| 42 | python | 3.11 | flask | PASS | PASS | PASS |
| 43 | python | 3.11 | streamlit | PASS | PASS | PASS |
| 44 | python | 3.11 | celery | PASS | PASS | PASS |
| 45 | python | 3.12 | generic | PASS | PASS | PASS |
| 46 | python | 3.12 | fastapi | PASS | PASS | PASS |
| 47 | python | 3.12 | django | PASS | PASS | PASS |
| 48 | python | 3.12 | flask | PASS | PASS | PASS |
| 49 | python | 3.12 | streamlit | PASS | PASS | PASS |
| 50 | python | 3.12 | celery | PASS | PASS | PASS |
| 51 | python | 3.13 | generic | PASS | PASS | PASS |
| 52 | python | 3.13 | fastapi | PASS | PASS | PASS |
| 53 | python | 3.13 | django | PASS | PASS | PASS |
| 54 | python | 3.13 | flask | PASS | PASS | PASS |
| 55 | python | 3.13 | streamlit | PASS | PASS | PASS |
| 56 | python | 3.13 | celery | PASS | PASS | PASS |
| 57 | python | 3.14 | generic | PASS | PASS | PASS |
| 58 | python | 3.14 | fastapi | PASS | PASS | PASS |
| 59 | python | 3.14 | django | PASS | PASS | PASS |
| 60 | python | 3.14 | flask | PASS | PASS | PASS |
| 61 | python | 3.14 | streamlit | PASS | PASS | PASS |
| 62 | python | 3.14 | celery | PASS | PASS | PASS |
| 63 | javascript | 18 | generic | PASS | PASS | PASS |
| 64 | javascript | 18 | express | PASS | PASS | PASS |
| 65 | javascript | 18 | react | PASS | PASS | PASS |
| 66 | javascript | 20 | generic | PASS | PASS | PASS |
| 67 | javascript | 20 | express | PASS | PASS | PASS |
| 68 | javascript | 20 | react | PASS | PASS | PASS |
| 69 | javascript | 22 | generic | PASS | PASS | PASS |
| 70 | javascript | 22 | express | PASS | PASS | PASS |
| 71 | javascript | 22 | react | PASS | PASS | PASS |
| 72 | typescript | 18 | generic | PASS | PASS | PASS |
| 73 | typescript | 18 | nestjs | PASS | PASS | PASS |
| 74 | typescript | 18 | nextjs | PASS | PASS | PASS |
| 75 | typescript | 20 | generic | PASS | PASS | PASS |
| 76 | typescript | 20 | nestjs | PASS | PASS | PASS |
| 77 | typescript | 20 | nextjs | PASS | PASS | PASS |
| 78 | typescript | 22 | generic | PASS | PASS | PASS |
| 79 | typescript | 22 | nestjs | PASS | PASS | PASS |
| 80 | typescript | 22 | nextjs | PASS | PASS | PASS |
| 81 | go | 1.21 | generic | PASS | PASS | PASS |
| 82 | go | 1.21 | gin | PASS | PASS | PASS |
| 83 | go | 1.21 | fiber | PASS | PASS | PASS |
| 84 | go | 1.22 | generic | PASS | PASS | PASS |
| 85 | go | 1.22 | gin | PASS | PASS | PASS |
| 86 | go | 1.22 | fiber | PASS | PASS | PASS |
| 87 | go | 1.23 | generic | PASS | PASS | PASS |
| 88 | go | 1.23 | gin | PASS | PASS | PASS |
| 89 | go | 1.23 | fiber | PASS | PASS | PASS |
| 90 | rust | 1.89 | generic | PASS | PASS | PASS |
| 91 | rust | 1.89 | actix | PASS | PASS | PASS |
| 92 | rust | 1.93 | generic | PASS | PASS | PASS |
| 93 | rust | 1.93 | actix | PASS | PASS | PASS |
| 94 | ruby | 3.2 | generic | PASS | PASS | PASS |
| 95 | ruby | 3.2 | rails | PASS | PASS | PASS |
| 96 | ruby | 3.3 | generic | PASS | PASS | PASS |
| 97 | ruby | 3.3 | rails | PASS | PASS | PASS |
| 98 | ruby | 3.4 | generic | PASS | PASS | PASS |
| 99 | ruby | 3.4 | rails | PASS | PASS | PASS |
| 100 | php | 8.2 | generic | PASS | PASS | PASS |
| 101 | php | 8.2 | laravel | PASS | PASS | PASS |
| 102 | php | 8.3 | generic | PASS | PASS | PASS |
| 103 | php | 8.3 | laravel | PASS | PASS | PASS |
| 104 | php | 8.4 | generic | PASS | PASS | PASS |
| 105 | php | 8.4 | laravel | PASS | PASS | PASS |
| 106 | dotnet | 8.0 | generic | PASS | PASS | PASS |
| 107 | dotnet | 8.0 | aspnet | PASS | PASS | PASS |
| 108 | dotnet | 9.0 | generic | PASS | PASS | PASS |
| 109 | dotnet | 9.0 | aspnet | PASS | PASS | PASS |
| 110 | csharp | 8.0 | generic | PASS | PASS | PASS |
| 111 | csharp | 8.0 | aspnet | PASS | PASS | PASS |
| 112 | csharp | 9.0 | generic | PASS | PASS | PASS |
| 113 | csharp | 9.0 | aspnet | PASS | PASS | PASS |
| 114 | kotlin | 1.9 | generic | PASS | PASS | PASS |
| 115 | kotlin | 1.9 | spring-boot | PASS | PASS | PASS |
| 116 | kotlin | 2.0 | generic | PASS | PASS | PASS |
| 117 | kotlin | 2.0 | spring-boot | PASS | PASS | PASS |
| 118 | scala | 2.13 | generic | PASS | PASS | PASS |
| 119 | scala | 2.13 | sbt | PASS | PASS | PASS |
| 120 | scala | 3.3 | generic | PASS | PASS | PASS |
| 121 | scala | 3.3 | sbt | PASS | PASS | PASS |

## Files Changed
| File | Purpose |
|---|---|
| `/mnt/c/Users/deepak/ai-folder/services/devops-tools-backend/app/services/pipeline/templates.py` | Durable source fix for version alias compatibility and reusable-template quality gates. |
| `/mnt/c/Users/deepak/ai-folder/services/devops-tools-backend/app/routers/pipeline.py` | Durable source fix for version-aware GitLab RAG lookup endpoint. |
| `/mnt/d/Repos/ai-folder/.Codex/live-backend/app/services/pipeline/templates.py` | Live backend mirror deployed into the running container. |
| `/mnt/d/Repos/ai-folder/.Codex/live-backend/app/routers/pipeline.py` | Live backend mirror deployed into the running container. |

## Commands Executed
| Command / Action | Outcome |
|---|---|
| `Chrome/Playwright full matrix through https://deepaksharma.live/pipelines: 363 checks` | PASS |
| `docker.exe cp patched backend files into devops-tools-backend` | PASS |
| `docker.exe restart devops-tools-backend` | PASS |
| `curl -k https://deepaksharma.live/api/v1/pipeline/providers health check` | PASS |
| `ChromaDB matrix count query across GitLab/Jenkins/Gitea collections` | PASS |
| `python3 -m py_compile patched backend files` | PASS |

## Artifacts
| Artifact | Path |
|---|---|
| Browser screenshot | `output/playwright/multi-language-version-matrix-summary.png` |
| Markdown report | `.Codex/reports/session-multi-language-version-rag-e2e-20260515.md` |
| JSON report | `.Codex/reports/session-multi-language-version-rag-e2e-20260515.json` |
| HTML report | `.Codex/reports/session-multi-language-version-rag-e2e-20260515.html` |

## Statistics
- Total browser checks: 363
- Logical language/version/framework combinations: 121
- Providers: 3
- Failures after fixes: 0
- ChromaDB matrix records verified: 605
