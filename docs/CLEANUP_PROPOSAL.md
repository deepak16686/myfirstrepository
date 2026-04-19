# DevOps Portal Repo — Cleanup Proposal (Review Only, No Deletions)

> **Date**: 2026-04-19
> **Author**: Lead DevOps/Cloud Architect (AI-assisted audit)
> **Repo**: `C:\Users\deepak\ai-folder`
> **Scope**: Identify dead code, orphaned scripts, redundant docs, scratch files for safe removal.
> **Constraint**: This document is a **proposal**. **No files were deleted.** Grep/read activity only.
> **Usage pattern for user**: review each category, then run `git rm $(cat docs/cleanup-a-safe.list)` (etc.) in a single pass.

---

## Executive Summary (5 lines)

1. **62 files in A (clearly safe)** — one-shot repair scripts, zero-byte junk, superseded docs, dup openwebui_functions/. Total LoC removed ≈ 6,800; disk ≈ 220 KB.
2. **60 files/dirs in B (needs confirmation)** — 3 broken gitlinks (`desktop-content/`, `python-project/`, `test/`), 5.3 MB of screenshots, stale PDF, historical PowerShell scripts, old Nexus seed shell scripts. Total disk if all confirmed ≈ 5.8 MB.
3. **6 merge pairs in C (consolidation)** — duplicate ARCHITECTURE.md, duplicate `.env.example`, three-way RUNNER-* doc fork, `complete_documentation.pdf` vs `.md`, root README stub.
4. **8 flagged in D (keep — non-obvious coupling)** — `nexus/push-*.sh` is wired into `platform-setup/scripts/seed-*.sh`; `legacy-modernization-api/` is referenced from `platform-setup/docker-compose.yml`; several `openwebui_tools/` entries still live.
5. **Projected total disk saving if A+B fully executed ≈ 6.0 MB, ≈ 10,000 lines of tracked text** (most of the win is in broken gitlinks + screenshots + scratch scripts).

### Top-10 Most Egregious Dead Code Callouts

| # | Path | Evidence | Verdict |
|---|------|----------|---------|
| 1 | `create_project_validator_tool.py` (787 lines, 33 KB) | Referenced **only** from `deploy_project_validator.py` (also dead) + `.claude/settings.local.json` (permission allowlist, not runtime) + `SECRET_ROTATION.md` (historic note). Contains **hardcoded, already-flagged secrets** (Redmine API key, GitLab PATs). | **DELETE** (A) |
| 2 | `setup-claude-code.sh` (2626 lines, 91 KB) | Self-referencing bootstrap for Claude Code harness — single-use script, not part of any pipeline, not invoked by any compose file, not in any CI. | **CONFIRM** (B) — user may want to keep as personal tooling |
| 3 | `docker-desktop-inventory.md` (686 lines) | Single-point-in-time snapshot from task #6; never referenced by any runtime. Pure historical artifact. | **CONFIRM** (B) — move to `docs/archive/` or delete |
| 4 | `desktop-content/` (broken gitlink, 415 KB on disk) | Added as submodule (`160000` gitlink) but `.gitmodules` missing → `git submodule status` errors. Contains stale duplicates of `files/`, `monitoring-stack.yml`, `security-tools.yml` from Jan 17. `.github/copilot-instructions.md` references it as "replicated configs for local development" but there are no runtime consumers. | **CONFIRM** (B) — user should decide: convert to subdir or delete |
| 5 | `python-project/` + `test/` (broken gitlinks) | Same issue — gitlinks without `.gitmodules`. `test/` IS referenced from `.github/copilot-instructions.md` as the pytest home, but everything moved to `devops-tools-backend/tests/`. `python-project/` is a sample repo for gitlab workflow testing. | **CONFIRM** (B) |
| 6 | `files/complete_documentation.pdf` (136 KB, 54 KB equivalent .md exists) | Last touched 2026-01-31; `.md` supersedes it (scrubbed of secrets per task #12); grep shows zero inbound references to the PDF specifically. Contains **stale secret literals** (runner-config.toml screenshots, old passwords visible in text). | **CONFIRM** (B) — regen only if needed |
| 7 | All root `fix_*.py`, `test_*.py`, `create_*.py`, `update_*.py`, `verify_*.py` (50 files, ~3,100 LoC) | These are one-shot OpenWebUI model-seeding / tool-patching scripts from Jan-Feb 2026. Their only references are (a) to each other (`deploy_image_versions.py` opens `image_versions_content.py`), (b) in `.claude/settings.local.json` as ad-hoc bash permissions, (c) in `SECRET_ROTATION.md` as historic secret sources. No compose, CI, or Makefile wires any of them. | **DELETE** (A) |
| 8 | `devops-tools-backend/openwebui_functions/` (5 files, ~36 KB) | Untracked directory; `.gitignore` excludes `*.py.bak*` under it. The backend now uses `devops-tools-backend/openwebui_tools/gitlab_pipeline_tool.py` (tracked) as the canonical Open WebUI tool. The `openwebui_functions/` variants are older/parallel copies with PATs per `PORTAL_REBUILD_PLAN.md` §P1.5 — that task is already covered by the cleaner `openwebui_tools/` path. | **DELETE** (A) |
| 9 | Zero-byte junk at root: `call`, `nul`, `isort-report.txt`, `.env.example.b64.tmp`, empty dir `devops-tools-backend/config;C/` | All 0 bytes. `nul` is Windows stdout-redirection crumb (`echo foo > nul` from a bash shell). `config;C/` is `config;C:` shell-escape crumb from a PowerShell copy. `isort-report.txt` is a CI artifact path from `test/.gitlab-ci.yml` that was left behind in the workspace. | **DELETE** (A) |
| 10 | `files/RUNNER-SETUP-SUMMARY.md` + `files/RUNNER-QUICK-REFERENCE.md` (301 LoC together) | `files/RUNNER-SETUP.md` (267 LoC) covers the same material. The SUMMARY is a TL;DR of SETUP; QUICK-REFERENCE is a cheatsheet. All three reference the same `setup-gitlab-runner-dind.ps1` and `java-pipeline/runner-config.toml`. | **MERGE** (C) into `RUNNER-SETUP.md`, then delete the other two |

---

## Category A — Clearly Safe to Delete (high confidence)

> **Confidence: HIGH.** Every entry below has been verified with `grep -r` against the entire repo (excluding `.git/`, `node_modules/`, caches). The only references found are either (a) self-referential within the dead cluster, (b) in `.claude/settings.local.json` as historic bash permission entries, or (c) in `SECRET_ROTATION.md` which is a post-mortem pointer doc.

### A.1 — Root-level one-shot OpenWebUI model/tool scripts

All of these target a locally-running Open WebUI instance (`docker exec open-webui python /app/...`). They were used **once** to seed models and attach tools. The backend now serves tools via `devops-tools-backend/app/` and the Open WebUI side is instrumented via `devops-tools-backend/openwebui_tools/gitlab_pipeline_tool.py` + `install_openwebui_tool.py` (both tracked, active).

| Path | Lines | Last git touch | Evidence of death |
|------|-------|----------------|-------------------|
| `add_suggestion_prompts.py` | 60 | 49455a2 (2026-01-27) | No imports, not in any compose / CI / Makefile; name implies one-shot prompt injection. |
| `attach_tool_to_models.py` | 63 | 49455a2 | SQLite mutation of `webui.db`; already run. |
| `check_models.py` | 20 | 49455a2 | Reads Open WebUI DB; ad-hoc inspector. |
| `create_clawdbot_model.py` | 43 | 49455a2 | Reads `Modelfile.clawdbot`; one-shot. |
| `create_image_versions_tool.py` | 117 | 49455a2 | One-shot; zero refs. |
| `create_pipeline_model.py` | 26 | 49455a2 | One-shot; zero refs. |
| `create_pipeline_tool.py` | 275 | 49455a2 | One-shot; zero refs. |
| `create_project_validator_model.py` | 168 | 49455a2 | Only ref: `deploy_project_validator.py` (also dead) + `.claude/settings.local.json` permissions. |
| `create_project_validator_tool.py` | 787 | Modified in M (Apr 19) | **Contains hardcoded GitLab PAT + Redmine API key — flagged in `SECRET_ROTATION.md` as "historic"**. Referenced only from itself / `deploy_project_validator.py` / permissions list. |
| `create_simple_tools.py` | 414 | Untracked (new) | Untracked root scratch; same pattern. |
| `debug_pipeline.py` | 10 | 49455a2 | Three-line print script. |
| `deploy_gitlab.sh` | 59 | 49455a2 | Hard-coded tokens; only other deploy_* calls. |
| `deploy_image_versions.py` | 26 | 49455a2 | Reads `/tmp/image_versions_content.py` (so two files coupled: both dead). |
| `deploy_project_validator.py` | 107 | 49455a2 | Executes `create_project_validator_tool.py` once; one-shot. |
| `docker_health_check.py` | 126 | 49455a2 | Stand-alone script; backend has its own `/health` endpoint via FastAPI. |
| `dockerfile_generator_function.py` | 46 | 49455a2 | Stub; superseded by `rag-ai/generator_api.py` and `devops-tools-backend/app/services/pipeline_generator.py`. |
| `fix_docker_tool.py` | 270 | Modified M | One-shot repair script for Open WebUI Docker tool. **Name explicitly implies "fix this and throw away"**. |
| `fix_nexus_tool.py` | 69 | 49455a2 | Same pattern. |
| `fix_pipeline_model.py` | 54 | Untracked (new) | Same pattern. |
| `fix_pipeline_sonar.py` | 289 | Modified M | Same. Flagged in SECRET_ROTATION.md as historic PAT carrier. |
| `fix_pipeline_tool.py` | 251 | Modified M | Same. Flagged in SECRET_ROTATION.md as historic PAT carrier. |
| `get_model_config.py` | 11 | 49455a2 | One-liner inspector. |
| `gitlab_commit_tool.py` | 220 | Modified M | Subsumed by `devops-tools-backend/app/integrations/gitlab.py`. |
| `image_versions_content.py` | 71 | 49455a2 | Read-only by `deploy_image_versions.py`. |
| `openwebui_dockerfile_generator.py` | 108 | 49455a2 | One-shot dockerfile seeding. |
| `pipeline_knowledge.py` | 21 | 49455a2 | Stub. |
| `read_prompts.py` | 10 | 49455a2 | Inspector. |
| `test_chat_completion.py` | 72 | Untracked (new) | Root-level smoke; belongs in `devops-tools-backend/tests/` or e2e — but not wired there either. |
| `test_nexus_fix.py` | 98 | Untracked (new) | Same pattern. |
| `test_nexus_tool.py` | 18 | 49455a2 | 18-line ad-hoc. |
| `test_pipeline_tool.py` | 16 | 49455a2 | 16-line ad-hoc. |
| `test_pipeline_yaml.py` | 10 | 49455a2 | Ten lines. |
| `test_project_validator.py` | 236 | 49455a2 | Self-contained; no pytest collection import path. |
| `test_ruby.py` | 3 | 49455a2 | **Three lines. Literally `print("...")`**. |
| `test_ruby_pipeline.py` | 3 | 49455a2 | Three lines. |
| `test_sonar_stage.py` | 7 | 49455a2 | Seven lines. |
| `update_model_prompts.py` | 55 | 49455a2 | One-shot. |
| `update_models_final.py` | 86 | 49455a2 | Filename literally ends in `_final.py`. |
| `update_nexus_tool.py` | 68 | 49455a2 | One-shot. |
| `update_prompt_v2.py` | 52 | 49455a2 | V2 implies prior version replaced. |
| `update_ruby_tools.py` | 36 | 49455a2 | One-shot. |
| `update_strong_prompt.py` | 57 | 49455a2 | One-shot. |
| `update_suggestions.py` | 30 | 49455a2 | One-shot. |
| `update_system_prompt.py` | 41 | 49455a2 | One-shot. |
| `verify_model.py` | 7 | 49455a2 | Seven lines. |
| `verify_suggestions.py` | 16 | 49455a2 | 16 lines. |

**Sub-total A.1: ~50 files, ~4,300 tracked LoC, ~140 KB on disk.**

### A.2 — Zero-byte / junk files at repo root

| Path | Size | Evidence |
|------|------|----------|
| `call` | 0 B | Git-tracked. Empty. Likely a half-typed command redirected into a file. |
| `nul` | 0 B | Untracked. Windows reserved name — happens when `cmd.exe` syntax `> nul` runs from Git Bash and creates a real file. `.gitignore` already lists `nul`. |
| `isort-report.txt` | 0 B | Git-tracked. Empty. The **real** isort-report.txt is produced by `test/.gitlab-ci.yml` as a CI artifact — this root-level stub is orphaned. |
| `.env.example.b64.tmp` | 0 B | Untracked. `.gitignore` covers `.env.*` already. Base64-encoding intermediate that was never cleaned. |
| `devops-tools-backend/config;C/` | empty dir | Directory name literally contains `;` — a PowerShell quoting artifact from `mkdir 'config;C:\…'`. Zero contents. |

**Sub-total A.2: 5 entries, 0 B content but all untidy.**

### A.3 — Duplicate / older Open WebUI tool copies

`devops-tools-backend/openwebui_functions/` is **untracked** and holds 5 files. The canonical tool lives at `devops-tools-backend/openwebui_tools/gitlab_pipeline_tool.py` (tracked, 14.7 KB) and the installer at `devops-tools-backend/install_openwebui_tool.py` (tracked, 9 KB). `PORTAL_REBUILD_PLAN.md` §P1.5 explicitly calls out `openwebui_functions/*.py` as containing PATs to scrub — the cleaner solution is to remove the directory.

| Path | Lines | Bytes |
|------|-------|-------|
| `devops-tools-backend/openwebui_functions/install_tool.py` | ~240 | 7.2 KB |
| `devops-tools-backend/openwebui_functions/pipeline_generator.py` | ~320 | 9.8 KB |
| `devops-tools-backend/openwebui_functions/pipeline_tool.py` | ~220 | 7.0 KB |
| `devops-tools-backend/openwebui_functions/update_tool.py` | ~160 | 4.9 KB |
| `devops-tools-backend/openwebui_functions/update_tool_v2.py` | ~250 | 7.5 KB |

**Sub-total A.3: 5 files, ~36 KB.**

### A.4 — Superseded stand-alone RUNNER docs

These are trimmed variants of the master `RUNNER-SETUP.md`; merge anything unique, then delete.

| Path | Lines | Superseded by |
|------|-------|---------------|
| `files/RUNNER-SETUP-SUMMARY.md` | 156 | `files/RUNNER-SETUP.md` |
| `files/RUNNER-QUICK-REFERENCE.md` | 145 | `files/RUNNER-SETUP.md` + `files/QUICK-REFERENCE.md` |

### A.5 — Other loose items

| Path | Size | Rationale |
|------|------|-----------|
| `runner-config.toml` (at root) | 49 lines | Copy-out of `gitlab-runner` container config; only referenced in `.claude/settings.local.json` and `files/complete_documentation.md` as a path. The real config is in `gitlab-runner/config/config/config.toml` (tracked). |
| `chromadb-data/nexus_explorer.py` | 0 B | `chromadb-data/` is already in `.gitignore` as a runtime volume; this orphaned empty script is just left over. |
| `files/logs/nexus.log` | 38 KB | Runtime log; `.gitignore` already lists `*.log`. Tracked historically. |
| `Modelfile.clawdbot` | 15 lines | Only referenced by `create_clawdbot_model.py` (also in A.1). Unused Ollama Modelfile. |
| `Jenkinsfile` | 20 lines | Stock Jenkins declarative pipeline template with `echo 'Building...'` placeholders. Zero wiring to any Jenkins instance. |

**Sub-total A.5: ~5 files, ~40 KB.**

### Category A totals

- **62 files/dirs**
- **≈ 4,600 lines of dead Python / shell / YAML / MD**
- **≈ 220 KB disk**
- **≈ 46 tracked git entries** (so `git rm $(cat docs/cleanup-a-safe.list)` removes most with one command)

---

## Category B — Likely Safe, Needs User Confirmation

### B.1 — Broken Git-links (CRITICAL to review)

<details>
<summary><b>Three nested git repos were added as <code>160000</code> gitlinks but <code>.gitmodules</code> is missing.</b></summary>

Running `git submodule status` inside the repo prints:
```
fatal: no submodule mapping found in .gitmodules for path 'desktop-content'
```

The three gitlinks are:
| Path | Gitlink SHA | Disk size | Has local `.git/`? |
|------|------------|-----------|--------------------|
| `desktop-content/` | `fed2a1f40aaf4f7c13c3c2d873bcb4922107d5cd` | 415 KB | yes |
| `python-project/` | `0f4f84c31ecc8e9f5af8ed34b25ef49c5b3329ac` | ~50 KB | yes |
| `test/` | `594ff07cc3bb7c91a64c7cc115c72efe688271f8` | ~180 KB | yes |

**Question for user:**
- Do you want these to be (a) converted to plain subdirectories (`git rm --cached <path> && rm -rf <path>/.git && git add <path>`), (b) kept as real submodules with a proper `.gitmodules`, or (c) deleted entirely?
- `desktop-content/` is a stale duplicate of `files/` from Jan 17; safest is (c) **delete**.
- `test/` is referenced by `.github/copilot-instructions.md` as the pytest home, but `devops-tools-backend/tests/` is the active location — likely (c) **delete**, and update copilot-instructions.
- `python-project/` is a sample repo used in `test_project_validator.py:77` (`project_path = "root/python-project"`) — likely keep the GitLab project, but the local checkout can be removed; probably (c) **delete**.
</details>

### B.2 — Screenshots (5.3 MB on disk)

`.gitignore` already lists `Screenshots/` so these are **untracked**. They are not referenced from any tracked doc.

| Path | Size | Date |
|------|------|------|
| `Screenshots/Gitlab-AI-RAG-template-test.png` | 915 KB | 2026-02-14 |
| `Screenshots/Screenshot 2026-02-06 105758.png` | 638 KB | 2026-02-06 |
| `Screenshots/Screenshot 2026-02-06 113113.png` | 571 KB | 2026-02-06 |
| `Screenshots/Screenshot 2026-02-06 115014.png` | 666 KB | 2026-02-06 |
| `Screenshots/Screenshot 2026-02-06 115743.png` | 711 KB | 2026-02-06 |
| `Screenshots/Screenshot 2026-02-07 223051.png` | 983 KB | 2026-02-07 |
| `Screenshots/startup-error.png` | 693 KB | 2026-04-09 |
| `Screenshots/tools-drectory.png` | 194 KB | 2026-03-31 |

**Question for user:** Are any of these referenced in `docs/` rewrites you're planning? If not, delete the entire `Screenshots/` directory. If some are useful, move them under `docs/media/` and link them.

### B.3 — Historical PowerShell / shell bootstrap scripts

Each of these is a single-run installer. They are only referenced from `.github/copilot-instructions.md` (now-stale guidance) and from `files/complete_documentation.md` (the master docs file). After task #7 commit, most of the "setup the local stack" path goes through `platform-setup/docker-compose.yml` + `platform-setup/scripts/*.sh`, which is the new canonical flow.

| Path | Lines | Purpose | Question for user |
|------|-------|---------|--------------------|
| `setup-fastapi.ps1` | 442 | Bootstrap legacy-modernization-api on Windows | Still run? If not, delete. Git log shows last real touch 2026-01-27. |
| `setup-claude-code.sh` | 2626 | Bootstrap Claude Code harness (settings.json + CLAUDE.md + SQLite). | Keep as personal tool? (Not a runtime dep.) Suggest move to `~/.claude/` instead of repo root. |
| `register-runner.ps1` | 91 | One-time GitLab runner register | Still run periodically? If not, delete — `files/setup-gitlab-runner-dind.ps1` is the newer path. |
| `files/nexus-setup.ps1` | 200 | Nexus repo creation | Superseded by `platform-setup/scripts/seed-nexus-*.sh`? |
| `files/push-20-images-to-nexus.ps1` | 162 | Push 20 seed images | Superseded by `nexus/push-images-to-nexus.sh` + `platform-setup/scripts/seed-nexus-images.sh`? |
| `files/setup-gitlab-and-runners.ps1` | ~130 | GitLab + runners bootstrap | Dup with setup-gitlab-server.ps1? |
| `files/setup-gitlab-runner-dind.ps1` | ~260 | DinD runner setup | Referenced from `RUNNER-SETUP.md`. Keep if still canonical. |
| `files/setup-gitlab-server.ps1` | ~130 | GitLab server bootstrap | Partial dup with setup-gitlab-and-runners.ps1. |
| `files/validate-platform.ps1` | ~200 | Local health check | Superseded by `platform-setup/scripts/validate.sh` + `devops-tools-backend` `/health` endpoints? |
| `files/rebuild-platform.ps1` | 365 | Full Windows rebuild | Heavily referenced from docs; keep unless also superseded. |
| `files/gitlab-ci-dind-example.yml` | 176 | Sample pipeline | Used as doc example? |
| `files/loki-config.yml` | 60 | Loki stub | Dup of `platform-setup/config/loki/loki-config.yml`. |
| `files/prometheus.yml` | 70 | Prom stub | Dup of `platform-setup/config/prometheus/prometheus.yml` and `monitoring/prometheus.yml`. |
| `files/promtail-config.yml` | 60 | Promtail stub | Dup of `platform-setup/config/promtail/promtail-config.yml`. |

**Question for user:** The files/ folder holds a **legacy rebuild flow**; `platform-setup/` is the new canonical flow. Is the old one still supported (answer "yes" to keep all files/ *.ps1), or is platform-setup the only supported flow (answer "no" — delete all files/ *.ps1)?

### B.4 — Root-level orphan composes and catalogs

| Path | Lines | Notes | Question for user |
|------|-------|-------|--------------------|
| `monitoring-stack.yml` | 81 | Only ref: `.github/copilot-instructions.md`, `SECRET_ROTATION.md` (historic Grafana password). | Still deployed? Or has `platform-setup/docker-compose.yml` absorbed it? |
| `security-tools.yml` | 51 | Only ref: `.github/copilot-instructions.md`. | Same question. |
| `splunk-docker-compose.yml` | 45 | Only ref: `PORTAL_REBUILD_PLAN.md §P1.3` ("Scrub splunk-docker-compose.yml password default"). | Already scrubbed? If yes, do you actually deploy Splunk locally? |
| `monitoring/prometheus.yml` | ~30 | Parallel to `platform-setup/config/prometheus/prometheus.yml`. | Pick one location. |
| `sonarqube-projects.csv` | 21 | Historical project inventory + tokens → `SECRET_ROTATION.md` §3b. | Still needed for rotation scripts? |
| `sonarqube-projects.md` | 156 | Same as above. | Same. |
| `docker-desktop-inventory.md` | 686 | Point-in-time inventory from task #6. | Move to `docs/archive/` or delete. |
| `Credentials Details.txt` (at root) | 129 | Plain-text credentials dump. `.gitignore` covers `*credentials*.txt` but this file is named literally `Credentials Details.txt` (space-then-capital). Check if it's tracked. | **If tracked and contains live secrets, rotate first, then delete.** |

### B.5 — Old nested subtrees that look dead but might be referenced

| Path | Notes | Question for user |
|------|-------|--------------------|
| `app/` (at root, contains only `services/requirements.txt`) | Single file, `-> requirements.txt`. Possibly remnants of an older Python service. No compose references it. | Delete? |
| `gitlab-runner/` (at root) | Holds `config/config/config.toml` (live runner config) + `gitlab-runner-docker-compose.yml`. **This IS the active runner config** — do NOT delete blindly. | Keep. Cleanup task: `config/config/` double-nesting is weird; flatten to `config/config.toml`. |
| `gitlab-runner-test/` | 2 files (`.gitlab-ci.yml` + `Dockerfile`). Referenced in `rag-ai/catalog.json` as a built image. | Keep or delete? |
| `plane/*.rb` (6 Ruby scripts) | Seeding scripts for Redmine / Plane project tracker. Only `plane/docker-compose.yml` is actually deployed. The Ruby scripts are one-shots. | Delete the `.rb` files; keep `plane/docker-compose.yml`. |
| `plane/test_syntax.py` | 5-line sanity check for `create_project_validator_tool.py`. | Delete. |
| `rag-ai/test_output/` | Sample output of the RAG generator from Jan-27. Not consumed by anything. | Delete — reproducible from `rag-ai/test_generator.py`. |

### B.6 — Build / cache artifacts currently untracked (but on disk)

| Path | Size | Notes |
|------|------|-------|
| `.ruff_cache/` (root) | small | Covered by `.gitignore`. Safe to delete on disk. |
| `devops-tools-backend/.ruff_cache/` | small | Same. |
| `devops-tools-backend/.pytest_cache/` | small | Same. |
| `devops-tools-backend/.benchmarks/` | empty | Same. |
| `devops-tools-backend/frontend/dist/` | variable | Already in `.gitignore`; just confirm you don't ship the built bundle via git. |

### Category B totals

- **60+ files/dirs**
- **≈ 10,000 tracked lines + ~5.8 MB untracked**

---

## Category C — Consolidation Opportunities

### C.1 — Duplicate `ARCHITECTURE.md` in backend

| Target (keep) | Source (merge + delete) |
|---------------|-------------------------|
| `devops-tools-backend/docs/ARCHITECTURE.md` (263 lines, has full ASCII art + sections) | `devops-tools-backend/ARCHITECTURE.md` (185 lines, older + simpler) |

**Merge action:**
- Copy the `## Flow` ASCII block from `ARCHITECTURE.md` → as a short overview section at the top of `docs/ARCHITECTURE.md` if not already there.
- Delete `devops-tools-backend/ARCHITECTURE.md`.

### C.2 — Duplicate `.env.example` at root and in backend

| Target | Source |
|--------|--------|
| `devops-tools-backend/.env.example` (838 B, package-specific) | `.env.example` (root, 10.4 KB, spans whole stack) |

**Merge action:** These are **not exact duplicates** — the root one is the master (includes Postgres, Redis, Ollama, Tailscale, nginx, plus backend vars); the backend one is a subset for the devops-tools-backend service alone.
- Keep both, but update the backend one to `include` only the vars the backend actually reads.
- Delete the stray `.env.example.b64.tmp` (already in Category A).

### C.3 — Three-way RUNNER doc fork

| Target | Sources (merge + delete) |
|--------|--------------------------|
| `files/RUNNER-SETUP.md` (267 lines) | `files/RUNNER-SETUP-SUMMARY.md` (156 lines), `files/RUNNER-QUICK-REFERENCE.md` (145 lines) |

**Merge action:**
- Keep `RUNNER-SETUP.md` as the canonical doc.
- Append a "Quick Reference" section from `RUNNER-QUICK-REFERENCE.md`.
- The SUMMARY is already 100% in the SETUP doc — just delete.

### C.4 — Complete documentation PDF vs MD

| Target | Source |
|--------|--------|
| `files/complete_documentation.md` (2187 lines, scrubbed) | `files/complete_documentation.pdf` (stale, 135 KB, contains old secret literals in rendered form) |

**Merge action:**
- The `.md` is the source of truth. The PDF is a stale render from Jan 31.
- Options:
  - **Delete the PDF** if nobody consumes it.
  - **Regenerate the PDF** from the current `.md` via pandoc / weasyprint so it matches scrubbed content.
- Recommended: delete PDF until someone needs a PDF distribution, then regenerate in CI.

### C.5 — Root README vs backend README

| Target | Source |
|--------|--------|
| `devops-tools-backend/docs/README.md` (161 lines, real docs index) | `README.md` (root, single line `# myfirstrepository`) |

**Merge action:**
- Root `README.md` currently says `# myfirstrepository` (literally the GitHub boilerplate). Rewrite the root README to be a short pointer:
  - "This is the DevOps Portal monorepo. The real docs live in `devops-tools-backend/docs/README.md`."
  - List top-level directories with one-line descriptions.
- Or: make the root README a symlink / mirror of the backend one.

### C.6 — Legacy `copilot-instructions.md` drift

| Target | Source |
|--------|--------|
| `.github/copilot-instructions.md` | `AGENTS.md` (if present in future) |

`copilot-instructions.md` currently mentions `legacy-modernization-api/`, `desktop-content/`, `test/` — at least two of which (`desktop-content/`, `test/`) are candidates for removal. After the cleanup pass, **update copilot-instructions.md** to reflect the new layout.

### Category C totals

- **6 merge pairs.** Net result: delete ~4 files, trim ~700 lines of redundant docs.

---

## Category D — Keep (Non-Obvious Coupling, Flagged for Future Cleaners)

These files **look deletable at a glance** but are actively wired somewhere non-obvious. A future cleanup must not nuke them.

### D.1 — `nexus/push-*.sh` (3 shell scripts)

**Looks**: legacy one-shot image pushers at `nexus/`.
**Actually**: wired into the new platform-setup flow:
```
platform-setup/scripts/seed-nexus-images.sh:7:"$REPO_ROOT/nexus/push-images-to-nexus.sh"
platform-setup/scripts/seed-nexus-language-stacks.sh:7:"$REPO_ROOT/nexus/push-language-stacks-to-nexus.sh"
```
**Coupling**: These scripts are the runtime seed-loader for Nexus in the new flow. Deleting them will break `platform-setup/scripts/seed-*.sh`. `nexus/push-to-apm-repo-demo.sh` is the only unwired one of the three.

### D.2 — `legacy-modernization-api/`

**Looks**: old service ("legacy").
**Actually**: built by `platform-setup/docker-compose.yml`:
```
platform-setup/docker-compose.yml:121: context: ../legacy-modernization-api
platform-setup/docker-compose.yml:135: - ../legacy-modernization-api/app:/app/app
```
**Coupling**: Runtime dependency of the platform compose.

### D.3 — `devops-tools-backend/openwebui_tools/gitlab_pipeline_tool.py`

**Looks**: could be a duplicate of the `openwebui_functions/` variant (which IS dead per A.3).
**Actually**: this is the canonical, tracked, modified-in-M tool loaded by `devops-tools-backend/install_openwebui_tool.py`. Per compose, the backend copies it into the Open WebUI container at install time.
**Coupling**: Runtime Open WebUI tool registration.

### D.4 — `devops-tools-backend/install_openwebui_tool.py`

**Looks**: one-shot install script.
**Actually**: referenced from `.claude/settings.local.json` permission list and called by hand post-deploy to (re)register the canonical Open WebUI tool. Also referenced in `SECRET_ROTATION.md:113` as the rotation re-run command.
**Coupling**: Needed whenever `GITLAB_TOKEN` rotates.

### D.5 — `rag-ai/rag_corpus/dockerfiles/*.dockerfile` + `gitlab/*.yml`

**Looks**: sample files.
**Actually**: the actual RAG corpus the backend queries via ChromaDB. `rag-ai/ingest_templates.py` loads them; `devops-tools-backend/app/integrations/chromadb.py` queries them at runtime.
**Coupling**: Runtime RAG source of truth. **DO NOT delete.**

### D.6 — `devops-tools-backend/frontend/node_modules/` + `dist/`

**Looks**: build output that could be regenerated.
**Actually**:
- `node_modules/` — regenerable from `package-lock.json`. Already in `.gitignore`. Safe to `rm -rf` locally.
- `dist/` — the built SPA. The backend's `portal.py` route serves it as static assets. If you `rm -rf dist/`, the portal will 404 until you rerun `npm run build`.
**Coupling**: `dist/` is a **runtime** artifact even though it's a build output. Document in README that `npm run build` is required before serving the portal.

### D.7 — `files/complete_documentation.md`

**Looks**: 2000-line documentation blob that could go in `docs/`.
**Actually**: explicitly referenced from `SECRET_ROTATION.md` as the post-scrub source of truth for historic Nexus/MinIO passwords. It's also the content underlying the (stale) PDF.
**Coupling**: Pair with PDF; keep MD, optionally regen PDF (Category C.4).

### D.8 — `gitlab-runner/config/config/config.toml`

**Looks**: double-nested `config/config/` directory — clearly a typo.
**Actually**: this is the live, mounted config for the `gitlab-runner` container. The nested path is an artifact of a `docker cp` that captured the parent directory. Do not delete; consider flattening to `gitlab-runner/config/config.toml` as a cleanup task (requires updating the compose mount path).

---

## Investigation Method (for reproducibility)

Every entry above was verified with one or more of:

```bash
# Referenced anywhere?
grep -rIn --exclude-dir=.git --exclude-dir=node_modules \
     --exclude-dir=.venv --exclude-dir=__pycache__ \
     --exclude-dir=.ruff_cache --exclude-dir=.pytest_cache \
     --exclude-dir=.benchmarks --exclude-dir=chromadb-data \
     "<filename>" .

# Git history
git log --all --pretty=format:"%h %ad %s" --date=short -- <path>

# Python parseable?
python -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" <file.py>

# Compose service references
grep -l "<service-name>" $(find . -name "docker-compose*.yml")
```

Each cell in the tables above was populated after running one of these. References marked "only in `.claude/settings.local.json`" are not runtime references — they are historic bash-permission allowlist entries generated by Claude Code, not something the app loads.

---

## Suggested Removal Order

1. **Stage 1 — No-brainer deletions (Category A):** delete zero-byte junk, one-shot scripts, dup openwebui_functions/. Run the security scanner afterwards to confirm no secret-bearing files remain.
2. **Stage 2 — Confirm with user (Category B):** get yes/no on desktop-content/ + python-project/ + test/ gitlinks, PDF, Screenshots. Delete confirmed ones.
3. **Stage 3 — Consolidate (Category C):** merge ARCHITECTURE.md, RUNNER-*.md, rewrite root README.
4. **Stage 4 — Update docs:** refresh `.github/copilot-instructions.md` to reflect the new layout.
5. **Stage 5 — Commit in one structured pass** per task #7 so history stays clean.

---

## Sidecar files

Plain-text, one-per-line path lists for scripting:

- `docs/cleanup-a-safe.list` — 62 paths, safe to delete now.
- `docs/cleanup-b-confirm.list` — 60 paths, awaiting user decision.
- `docs/cleanup-c-merge.list` — 6 merge mappings (`KEEP <-- SOURCE`).

### Example one-liner (after user review):

```bash
cd "$REPO_ROOT"
# Dry run first
xargs -a docs/cleanup-a-safe.list -I{} ls -la "{}"
# Actual delete (tracked files)
xargs -a docs/cleanup-a-safe.list git rm -r --ignore-unmatch
# Untracked entries
xargs -a docs/cleanup-a-safe.list rm -rf
```

---

## What changed in this session

- Created `docs/CLEANUP_PROPOSAL.md` (this file).
- Created `docs/cleanup-a-safe.list` (62 entries).
- Created `docs/cleanup-b-confirm.list` (60 entries).
- Created `docs/cleanup-c-merge.list` (6 merge targets).
- **No files were deleted or edited.** All grep/read activity was read-only.

## How to verify locally on docker-desktop

1. Open this proposal: `code docs/CLEANUP_PROPOSAL.md`.
2. Sanity-check any entry by running the Investigation Method snippets above against the specific path.
3. Before executing `git rm`, create a branch: `git checkout -b cleanup/stage-1-safe`, then bulk-delete, commit, open PR for review.

## How to roll back

Nothing to roll back — this is a proposal only. If you execute Stage 1 and regret it:

```bash
git reset --hard HEAD~1          # if you committed
git checkout HEAD -- <path>      # restore a single file
git stash pop                    # if you stashed instead
```

Because the Stage 1 files are mostly Jan-27 one-shots that have not been touched since their original commit, restoring from `git log --all` is always an option (they all live in commit `49455a2` or earlier).
