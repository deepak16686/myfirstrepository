#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# DevOps Portal — End-to-End Smoke Harness Runner
# ------------------------------------------------------------------------------
# Orchestrates:
#   1) smoke.py        — health-probes every tool in tools.yaml
#   2) vault_smoke.py  — Vault reachability + KV pointer presence
#   3) tool_login.py   — Playwright login checks (only if smoke passes)
#
# Aggregates all three JSON reports into scripts/e2e/report.json.
# Idempotent and safe to re-run. Never logs credential values.
#
# Prereqs (see scripts/e2e/README.md):
#   python -m venv .venv && source .venv/Scripts/activate
#   pip install -r scripts/e2e/requirements.txt
#   playwright install chromium
#   export GRAFANA_ADMIN_PASSWORD=... etc.
#
# Exit codes:
#   0  — everything green
#   1  — smoke or login failures
#   2  — vault warnings (e.g. VAULT_TOKEN not set)
#   10 — environment/prereqs missing (python not found etc.)
# ------------------------------------------------------------------------------

set -o errexit
set -o nounset
set -o pipefail

# --- Locate ourselves (Git Bash on Windows handles this fine) -----------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPORT_DIR="${SCRIPT_DIR}"
SMOKE_REPORT="${REPORT_DIR}/smoke-report.json"
VAULT_REPORT="${REPORT_DIR}/vault-report.json"
LOGIN_REPORT="${REPORT_DIR}/login-report.json"
FINAL_REPORT="${REPORT_DIR}/report.json"

cd "${REPO_ROOT}"

# --- Colour helpers (opt-out if not a TTY) ------------------------------------
if [[ -t 1 ]]; then
  C_OK=$'\033[32m'
  C_WARN=$'\033[33m'
  C_FAIL=$'\033[31m'
  C_INFO=$'\033[36m'
  C_RESET=$'\033[0m'
else
  C_OK=''
  C_WARN=''
  C_FAIL=''
  C_INFO=''
  C_RESET=''
fi

info()  { echo "${C_INFO}[run-all]${C_RESET} $*"; }
ok()    { echo "${C_OK}[run-all]${C_RESET} $*"; }
warn()  { echo "${C_WARN}[run-all]${C_RESET} $*"; }
fail()  { echo "${C_FAIL}[run-all]${C_RESET} $*" >&2; }

# --- Load .env if present -----------------------------------------------------
# Accepts .env in the e2e dir OR the repo root. Never clobbers pre-exported
# vars — shell's existing environment wins.
load_env() {
  local env_file="$1"
  if [[ -f "${env_file}" ]]; then
    info "loading env from ${env_file}"
    # Use `set -a` so all assignments export, but respect existing values
    # by only defaulting. Reading a line at a time is safer than `source`
    # because it tolerates comments and keys with spaces/equals in values.
    while IFS= read -r line || [[ -n "${line}" ]]; do
      # Strip leading whitespace, skip blank lines and comments.
      local trimmed
      trimmed="$(printf '%s' "${line}" | sed -e 's/^[[:space:]]*//')"
      [[ -z "${trimmed}" || "${trimmed}" == \#* ]] && continue
      # Only accept KEY=VALUE; drop "export" prefix if present.
      trimmed="${trimmed#export }"
      if [[ "${trimmed}" != *=* ]]; then
        continue
      fi
      local key="${trimmed%%=*}"
      local value="${trimmed#*=}"
      # Strip optional surrounding single or double quotes.
      if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
        value="${value:1:${#value}-2}"
      fi
      if [[ -z "${!key-}" ]]; then
        export "${key}=${value}"
      fi
    done < "${env_file}"
  fi
}

load_env "${SCRIPT_DIR}/.env"
load_env "${REPO_ROOT}/.env"

# --- Locate Python ------------------------------------------------------------
PY=""
for candidate in "python" "python3" "py"; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    PY="${candidate}"
    break
  fi
done
if [[ -z "${PY}" ]]; then
  fail "no python interpreter found on PATH (looked for python, python3, py)"
  exit 10
fi
info "using python: $(${PY} --version 2>&1)"

# --- Housekeeping -------------------------------------------------------------
mkdir -p "${SCRIPT_DIR}/artifacts"
rm -f "${SMOKE_REPORT}" "${VAULT_REPORT}" "${LOGIN_REPORT}" "${FINAL_REPORT}"

# --- Phase 1: smoke -----------------------------------------------------------
info "phase 1/3 — smoke.py"
set +o errexit
"${PY}" "${SCRIPT_DIR}/smoke.py" \
  --registry "devops-tools-backend/config/tools.yaml" \
  --report "${SMOKE_REPORT}"
SMOKE_RC=$?
set -o errexit
if [[ ${SMOKE_RC} -ne 0 ]]; then
  fail "smoke.py exited ${SMOKE_RC} — skipping tool_login.py"
else
  ok "smoke.py passed"
fi

# --- Phase 2: vault -----------------------------------------------------------
info "phase 2/3 — vault_smoke.py"
set +o errexit
"${PY}" "${SCRIPT_DIR}/vault_smoke.py" \
  --registry "devops-tools-backend/config/tools.yaml" \
  --report "${VAULT_REPORT}"
VAULT_RC=$?
set -o errexit
case "${VAULT_RC}" in
  0) ok "vault_smoke.py passed" ;;
  2) warn "vault_smoke.py warnings (rc=${VAULT_RC})" ;;
  *) fail "vault_smoke.py failed (rc=${VAULT_RC})" ;;
esac

# --- Phase 3: login (only if smoke passed) ------------------------------------
LOGIN_RC=0
if [[ ${SMOKE_RC} -eq 0 ]]; then
  info "phase 3/3 — tool_login.py"
  set +o errexit
  "${PY}" "${SCRIPT_DIR}/tool_login.py" \
    --report "${LOGIN_REPORT}"
  LOGIN_RC=$?
  set -o errexit
  if [[ ${LOGIN_RC} -eq 0 ]]; then
    ok "tool_login.py passed"
  else
    fail "tool_login.py failed (rc=${LOGIN_RC})"
  fi
else
  warn "phase 3/3 — tool_login.py skipped because smoke failed"
  LOGIN_RC=-1
fi

# --- Aggregation --------------------------------------------------------------
info "aggregating reports into ${FINAL_REPORT}"
"${PY}" - <<PY_EOF
import json
from datetime import datetime, timezone
from pathlib import Path

def load(p):
    q = Path(p)
    if not q.exists():
        return None
    try:
        return json.loads(q.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"{e.__class__.__name__}: {e}"}

agg = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "smoke": load("${SMOKE_REPORT}"),
    "vault": load("${VAULT_REPORT}"),
    "login": load("${LOGIN_REPORT}"),
    "rc": {
        "smoke": ${SMOKE_RC},
        "vault": ${VAULT_RC},
        "login": ${LOGIN_RC},
    },
}
Path("${FINAL_REPORT}").write_text(
    json.dumps(agg, indent=2, sort_keys=True, default=str),
    encoding="utf-8",
)
PY_EOF

ok "aggregated report -> ${FINAL_REPORT}"

# --- Exit code policy ---------------------------------------------------------
# Hard fail (1) wins over warn (2). Login skip is neutral (-1).
if [[ ${SMOKE_RC} -ne 0 || ${LOGIN_RC} -gt 0 ]]; then
  fail "RESULT: FAIL"
  exit 1
fi
if [[ ${VAULT_RC} -eq 2 ]]; then
  warn "RESULT: PASS with warnings"
  exit 2
fi
if [[ ${VAULT_RC} -ne 0 ]]; then
  fail "RESULT: FAIL (vault)"
  exit 1
fi
ok "RESULT: PASS"
exit 0
