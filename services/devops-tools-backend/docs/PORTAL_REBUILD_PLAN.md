# DevOps Portal — End-to-End Rebuild Plan

**Status:** Active
**Owner:** Deepak
**Start:** 2026-04-19
**Scope:** Rebuild `devops-tools-backend/frontend/` into a professional DevOps portal that unifies every running tool on Docker Desktop, exposes it via Tailscale Funnel, preserves every existing named volume, and ships with proper repo organization + committed changes.

---

## 1. Context (from discovery)

- **76 running containers** across 5 compose projects: `infra-stack` (35), `chaos-platform-setup` (18), `brandmatik` (13), `taskflow` (5), `dev-stack` (2).
- Portal is primarily for the **infra-stack + dev-stack** tools (the real DevOps/AI platform). Brandmatik/Chaos/Taskflow appear as three "Projects" cards linking to their gateways.
- Existing frontend is plain HTML/JS chat at `devops-tools-backend/frontend/`. **Full rebuild required.**
- Backend FastAPI on :8003 has 73 endpoints across 8 routers. Only 6 of 76+ tools are wrapped. Portal-side API (`/api/v1/portal/*`) doesn't exist yet.
- **No canonical tool registry existed** — fixed by introducing `devops-tools-backend/config/tools.yaml` (v1, this turn).
- **4 real GitLab PATs** exposed in `devops-tools-backend/openwebui_functions/*.py` + hardcoded passwords in compose + k8s manifests. Must rotate + scrub before commit.
- Tailscale v1.96.3 installed but logged out. MagicDNS `deepak-desktop.tailac51e7.ts.net`. One `tailscale up` restores funnel.

---

## 2. Architecture decisions

1. **Frontend stack**: Vite 5 + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui + Tanstack Query. Industry standard for modern SaaS dashboards; familiar patterns, shadcn tokens give us a distinctive dark-first look without custom CSS.
2. **Deployment**: Built SPA mounted via FastAPI `StaticFiles` at `/` (single port, single Tailscale Funnel). Dev mode uses Vite on :5173 with proxy to backend `/api`.
3. **Tool catalog**: YAML file (`config/tools.yaml`) loaded by backend. Hot-reload optional via file-mtime check; restart acceptable for v1.
4. **Health strategy**: backend probes every tool on interval (30s) + on-demand. Results cached in Redis (already running) with 15s TTL. Portal reads aggregate via `/api/v1/portal/health`.
5. **Launch semantics**: three modes per tool — `external` (open in new tab pointing at `url_external`), `embed` (iframe inside portal for tools where `embed: true`), `docs` (link to `/docs` for swagger).
6. **Auth**: v1 = Tailscale identity only (tailnet membership = access). No per-tool SSO. Tailscale Funnel route will be public and optionally IP-limited.
7. **Volume preservation**: all compose `up` / rebuild operations use existing named volumes verbatim — no `docker volume rm`, no `docker compose down -v`. Volumes of concern: `nexus-data` (38.2GB), `ollama` (23.4GB), `splunk-*` (2.8GB), `jira_data`, `prometheus-data`, `grafana-*`, all Postgres PVs.
8. **Network**: portal container (if run separately) + backend both attach to existing `global-infra-net` to resolve every tool by container name.
9. **Tailscale**: `tailscale up` → `tailscale serve https / proxy 8003` → `tailscale funnel 443 on`. Single HTTPS endpoint for the portal.
10. **Secrets**: all live values move to Vault (already running on :8200). `.env` files gitignored. Compose reads `${VAR}` with zero fallback values.

---

## 3. Execution phases

### P0 — Fast wins (parallel)
- P0.1  Fix `.gitignore` to cover Screenshots/, .claude/, openwebui_functions/ PAT files, nul, config;C/.
- P0.2  Bring Tailscale online (`tailscale up`) — user-initiated action.

### P1 — Secrets remediation (blocks all commits)
- P1.1  Identify every hardcoded secret (4 PATs + 5 passwords confirmed in audit).
- P1.2  Scrub compose file defaults (`SONARQUBE_PASSWORD=`, etc.) — require env or fail.
- P1.3  Scrub `splunk-docker-compose.yml` password default.
- P1.4  Scrub k8s-prod/manifests/*.yaml passwords → reference `envFrom: secretRef:`.
- P1.5  Scrub openwebui_functions/*.py PATs → require env var.
- P1.6  Write `.env.example` at root with all variables (no values).
- P1.7  Rotation instructions for the 2 distinct GitLab PATs — **user-action**.

### P2 — Tool registry ✅ (delivered this turn)
- `devops-tools-backend/config/tools.yaml` seeded with 34 primary tools.

### P3 — Backend portal API
- P3.1  New router `app/routers/portal.py` mounted at `/api/v1/portal`.
- P3.2  `GET /api/v1/portal/tools` — loads `config/tools.yaml`, enriches with live health from cache, returns full catalog.
- P3.3  `GET /api/v1/portal/tools/{id}` — single tool detail.
- P3.4  `GET /api/v1/portal/health` — aggregated health with `{tool_id: {status, latency_ms, last_checked}}`.
- P3.5  `GET /api/v1/portal/health/{id}` — force re-probe.
- P3.6  `GET /api/v1/portal/categories` — category metadata.
- P3.7  `POST /api/v1/portal/launch/{id}` — idempotent "launch prep" (seed auth cookie if needed, return redirect URL).
- P3.8  Background task: probe every tool every 30s, write results to Redis key `portal:health:{id}` TTL 60s.
- P3.9  Update `app/main.py` to include portal router.
- P3.10 Update `app/config.py` with `TOOLS_REGISTRY_PATH` setting.

### P4 — Portal frontend
- P4.1  Scaffold Vite React TS Tailwind shadcn under `devops-tools-backend/frontend/`.
- P4.2  Global layout: sidebar (categories) + topbar (search, theme toggle, user) + content area.
- P4.3  Landing: dashboard tiles (total tools, healthy %, critical issues, pipelines running last 24h).
- P4.4  Tool grid: card per tool (icon, name, category badge, health dot, quick actions).
- P4.5  Tool detail drawer: full info, launch/embed/docs buttons, live health sparkline.
- P4.6  Embed mode: iframe wrapper with safety headers, back button, fullscreen toggle.
- P4.7  Search + category filter + tag chip filter.
- P4.8  Dark mode default, light toggle; respects `prefers-color-scheme`.
- P4.9  Pipelines page: table of recent GitLab pipeline runs (reuses `/api/v1/gitlab/...`).
- P4.10 Chat page: migrates existing chat UI to shadcn components (keeps `/api/v1/chat/`).
- P4.11 Build script: `pnpm build` → `dist/` → copied into backend `frontend/` dir.
- P4.12 Update backend `app/main.py` to serve new SPA (index.html + `/assets/*` fallthrough).

### P5 — Integration wrappers (incremental)
- P5.1  Stub integration classes for remaining tools: Jenkins, Grafana, Prometheus, Loki, Jaeger, MinIO, Redis, Postgres, Splunk, Redmine, Jira, Vault.
- P5.2  Implement read-only probes for each (no write ops). Enough for portal health.
- P5.3  Full wrappers deferred — portal v1 works off HTTP probes alone.

### P6 — Tailscale Funnel wiring
- P6.1  `tailscale up` (user).
- P6.2  `tailscale serve --bg https / proxy 8003`.
- P6.3  `tailscale funnel --bg 443 on`.
- P6.4  Verify `https://deepak-desktop.tailac51e7.ts.net/` from external network.
- P6.5  Optional: reverse ACL to limit to specific tailnet tags.

### P7 — Preserve volumes + bring up stack
- P7.1  Snapshot-list every named volume with size (baseline).
- P7.2  Run `docker compose up -d --no-recreate` for each compose project (reuses volumes).
- P7.3  Post-up verify: same volumes still attached, sizes match baseline ±epsilon.
- P7.4  Fix anything broken (chatbot-portal ignored — external source).

### P8 — E2E test (Chrome DevTools MCP)
- P8.1  Open `http://localhost:8003/` — portal loads.
- P8.2  For every tool card in the registry: click → verify launch target responds 2xx.
- P8.3  Health indicators match backend probes.
- P8.4  Search + filter + theme toggle work.
- P8.5  External Funnel URL loads identical content.

### P9 — Repo organization + structured commits
- P9.1  Apply `.gitignore` updates; verify clean status.
- P9.2  Move root-level Python ops scripts under `scripts/{install,fix,update,test}/`.
- P9.3  Commit sequence (one commit per concern, signed off):
  1. `.gitignore + secrets scrub` — prevents accidental re-leak.
  2. `backend: migrate ChromaDB v1→v2, add RL pipeline` — the 13 modified files.
  3. `backend: add chat router + service` — new files.
  4. `backend: add portal router + tool registry` — P2+P3 deliverables.
  5. `frontend: new Vite/React/TS/Tailwind/shadcn portal` — P4 deliverables.
  6. `docs: ARCHITECTURE, API, CREDENTIALS, DIAGRAMS, RL` — untracked docs.
  7. `k8s: production manifests (secrets scrubbed)`.
  8. `rag-ai: add golang templates`.
  9. `misc: splunk-docker-compose, scripts reorg`.
- P9.4  `git push origin master`.

### P10 — Docs
- P10.1 Top-level `README.md` with architecture diagram + quickstart.
- P10.2 `docs/adr/0001-devops-portal-stack.md` — framework choice rationale.
- P10.3 `docs/RUNBOOK.md` — start/stop/rebuild per compose project.
- P10.4 `docs/TAILSCALE.md` — funnel setup + recovery.

---

## 4. Parallel execution groups

**Wave A (now, parallel):**
- frontend-engineer → P4.1–P4.12 (portal build)
- backend-engineer → P3.1–P3.10 (portal API)
- security-engineer → P1.1–P1.7 (secrets)

**Wave B (after Wave A):**
- P5 (integration wrappers)
- P7 (volume-preserving bring-up)

**Wave C:**
- P6 (Tailscale) + P8 (E2E test)

**Wave D:**
- P9 + P10 (commits + docs)

---

## 5. Volume preservation contract

Never to be violated:
- No `docker volume rm`
- No `docker compose down -v`
- No `docker system prune -a --volumes`
- `docker compose up` always with `--no-recreate` unless service config actually changed and volumes are re-referenced by the same names
- Before any compose config change touching `volumes:`, snapshot size baseline and verify post-change match

Critical volumes (size):
- nexus-data 38.2 GB
- ollama 23.4 GB
- prod-splunk-var 1.4 GB · prod-splunk-etc 1.4 GB
- prometheus-data 1.3 GB
- trivy-cache 1.0 GB
- jira_data 972 MB
- loki-data 395 MB
- sonarqube-data 327 MB
- all Postgres PVs (aggregate < 500 MB but irreplaceable)
- grafana-storage, minio-data, redis-data, gitea-data, gitlab-* volumes (smaller, still irreplaceable)

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Accidental `down -v` during rebuilds | Rule baked into agent prompts + no destructive flag in any script. |
| PAT leak into remote once pushed | P1 scrub runs before P9 commits; PATs gitignored even after scrub. |
| Portal exposes tool admin UIs publicly via Funnel | Funnel routes only the portal itself; embedded tool UIs still need their own creds. Tailscale tag ACL optional. |
| Backend load from health probes | 30s interval, 4s timeout, Redis cache TTL 60s. Max ~3 QPS across 34 tools. |
| Vite HMR not reachable on :5173 through Funnel | Dev mode is local-only; Funnel only serves production build on :8003. |
| ChromaDB v2 migration ongoing — tests may break | Separate tracking; does not block portal. Backend already modified. |

---

## 7. Rollback

- **Frontend**: `git restore devops-tools-backend/frontend/` brings back 3-file chat UI. Backend still serves `/` via old StaticFiles mount.
- **Backend**: `app/routers/portal.py` + include_router line reverted; tool registry file untouched.
- **Tailscale**: `tailscale funnel 443 off` + `tailscale serve reset`.
- **Compose**: every change is additive or env-var-only; `git restore` on compose files restores prior wiring. No volume state lost since no destructive op was performed.

---

*Generated by main orchestrator; consumed by wave-A worker agents.*
