# DevOps Portal — End-to-End Smoke + Login Harness

Manual operator harness for the DevOps Portal tool registry (33 tools
defined in `devops-tools-backend/config/tools.yaml`). Run this *after*
bringing the Docker Desktop stack up — it will fail loudly if anything
is offline.

## Contents

| File | Purpose |
|------|---------|
| `smoke.py`        | Async GET health-probe against every `url_external` + `health.method == GET` tool. Also asserts the portal's `/api/v1/portal/stats` reports >= 30 tools. |
| `vault_smoke.py`  | Verifies Vault is reachable and that every `vault:<path>` pointer in `tools.yaml` has a readable KV entry. |
| `tool_login.py`   | Playwright-driven login checks for Grafana, GitLab, SonarQube, Nexus, Jenkins. Takes a screenshot on success and failure. |
| `run-all.sh`      | Bash orchestrator — runs the three phases, aggregates reports into `report.json`. |
| `requirements.txt`| Pinned deps for a virtualenv. |
| `artifacts/`      | Screenshot output from `tool_login.py`. |

## Coverage

- `smoke.py` covers **28 of 33** registry tools (the 5 that use
  `docker_ps` / `docker_exec` health methods are skipped by design —
  running a cross-host `docker exec` from this harness would break its
  "anonymous HTTP only" contract).
- `vault_smoke.py` covers all **12** tools whose credentials are
  `vault:secret/devops/<tool>/<role>` pointers.
- `tool_login.py` covers the **5 highest-value tools** (Grafana,
  GitLab, SonarQube, Nexus, Jenkins).

## Prerequisites

- Docker Desktop stack is UP (tools listening on the localhost ports
  listed in `tools.yaml`).
- Tailscale funnel up if you want to run against a remote base URL
  (use `smoke.py --base-external https://ai.tailnet.ts.net`).
- Python 3.11+ on PATH.
- For `tool_login.py`: `playwright install chromium` has been run.

## Quickstart (Windows Git Bash)

```bash
cd scripts/e2e
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

# Required for tool_login.py — the harness NEVER falls back to
# defaults or hard-codes anything. Missing env vars mean "SKIP".
export GRAFANA_ADMIN_PASSWORD='...'
export GITLAB_ROOT_PASSWORD='...'
export SONARQUBE_ADMIN_PASSWORD='...'
export NEXUS_ADMIN_PASSWORD='...'
export JENKINS_ADMIN_PASSWORD='...'

# Optional — defaults are 'admin' everywhere except GitLab ('root')
# export GRAFANA_USERNAME=admin
# export GITLAB_USERNAME=root
# export SONARQUBE_USERNAME=admin
# export NEXUS_USERNAME=admin
# export JENKINS_USERNAME=admin

# Optional — needed by vault_smoke.py for KV lookups
export VAULT_ADDR='http://localhost:8200'
export VAULT_TOKEN='hvs.xxxxxxxxxxxxxxxx'

./run-all.sh
```

## Individual scripts

```bash
# Smoke only
python smoke.py --registry ../../devops-tools-backend/config/tools.yaml

# Subset — space/newlines are tolerated; commas are the separator
python smoke.py --only grafana,prometheus,loki --json

# Remote run via Tailscale funnel
python smoke.py --base-external https://ai.tailnet.ts.net

# Fail-fast mode
python smoke.py --fail-fast

# Login a single tool with JSON report
python tool_login.py --only grafana --report grafana.json

# Vault only
python vault_smoke.py --vault-addr http://localhost:8200 --json
```

## JSON report schema

`run-all.sh` writes `report.json` with this shape:

```json
{
  "generated_at": "2026-04-19T17:32:14+00:00",
  "rc": { "smoke": 0, "vault": 0, "login": 0 },
  "smoke": {
    "summary": { "total": 28, "ok": 27, "fail": 1, "skip": 0, "portal_ok": true },
    "portal_stats": { "...": "..." },
    "results": [{"tool_id": "grafana", "status": "OK", "...": "..."}]
  },
  "vault": {
    "summary": { "total": 13, "ok": 13, "fail": 0, "warn": 0, "skip": 0,
                 "token_present": true, "vault_addr": "http://localhost:8200" },
    "checks": [{"kind": "HEALTH", "subject": "...", "status": "OK"}]
  },
  "login": {
    "summary": { "pass": 5, "fail": 0, "skip": 0, "total": 5 },
    "results": [{"tool": "grafana", "status": "PASS", "screenshot": "..."}]
  }
}
```

## Credential safety

- No password is ever printed, logged, or persisted. When env vars are
  missing the harness emits `MISSING env <VARNAME>` — never the value.
- Screenshots are taken on the target application's landing page, not
  the login form after submission — avoid password autofill leakage.
- `report.json` contains no credential values. Only status, URL, HTTP
  code, timing, and non-sensitive user identifiers (e.g. `login:"admin"`
  returned by `/api/user`).

## Idempotence

- All scripts are read-only against the target systems (GET, or POST
  against login endpoints which create short-lived sessions — no
  mutations).
- Re-runs overwrite prior `report.json` and prior screenshots share
  timestamped filenames so they accumulate (delete `artifacts/` to
  reset).
- Vault KV lookups use `metadata` reads where possible — they never
  pull the secret payload.

## Exit codes

| Code | Meaning |
|------|---------|
| 0    | All phases green. |
| 1    | smoke failure, login failure, or vault reachability failure. |
| 2    | PASS with warnings (e.g. `VAULT_TOKEN` unset, so KV checks were skipped). |
| 10   | Environment setup missing (no Python interpreter). |

## Troubleshooting

- `connection refused` on most tools → Docker Desktop is down or the
  compose stack hasn't finished starting. `docker compose ps` should
  show everything healthy. Re-run after 30 seconds.
- `playwright` errors about "Executable doesn't exist" → run
  `playwright install chromium` inside the venv.
- Vault `403 forbidden` on KV → your `VAULT_TOKEN` doesn't have a read
  policy for `secret/devops/*`. Mint a token with `vault write auth/token/create policies=devops-read`.
- Playwright `TimeoutError` on GitLab → GitLab typically needs 3-5
  minutes to boot after `docker compose up`; `GET /-/readiness` returns
  503 until it's ready.

## Rollback

This harness is **purely observational** — there is nothing to roll
back. To uninstall:

```bash
# inside scripts/e2e
rm -rf .venv artifacts/ report.json smoke-report.json vault-report.json login-report.json
```

The scripts are self-contained in `scripts/e2e/` and do not touch the
backend, Docker, or Vault beyond read-only API calls.
