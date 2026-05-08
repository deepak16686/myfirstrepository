#!/usr/bin/env bash
# =============================================================================
# bootstrap-funnel.sh
# -----------------------------------------------------------------------------
# Wire the DevOps Portal + Grafana + GitLab onto Tailscale Funnel, and every
# other tool onto tailscale-serve (tailnet-only). Intended to run inside WSL
# (Ubuntu) against the Windows host's tailscaled. It applies the declarative
# serve-config.json and then toggles funnel on for the three public slots.
#
# Usage:
#   ./tailscale/bootstrap-funnel.sh          # apply
#   ./tailscale/bootstrap-funnel.sh --reset  # wipe serve + funnel, keep daemon
#   ./tailscale/bootstrap-funnel.sh --status # show current serve/funnel state
#
# Safe re-run: idempotent. `tailscale serve set-config` is a declarative
# replace, so running twice yields the same state.
#
# Cap-of-3 awareness: Tailscale Free allows up to 3 concurrent funnel
# host:port tuples. serve-config.json has AllowFunnel:true on exactly 3
# entries (deepaksharma.live, grafana.deepaksharma.live, gitlab.deepaksharma.live).
# If you hand-edit and add a 4th, `tailscale set-config` will refuse.
# =============================================================================

set -euo pipefail

# ----- Paths & constants -----------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/serve-config.json"

# Funnel slot hostnames we expect to come up.
PUBLIC_HOSTS=(
  "deepaksharma.live"
  "grafana.deepaksharma.live"
  "gitlab.deepaksharma.live"
)

# Tailnet MagicDNS name of this node (used for cert check + diagnostic curl).
TAILNET_HOST="deepak-desktop.tailac51e7.ts.net"

# ----- Pretty print helpers --------------------------------------------------
C_RESET="\033[0m"; C_BOLD="\033[1m"; C_GREEN="\033[32m"
C_YELLOW="\033[33m"; C_RED="\033[31m"; C_BLUE="\033[34m"

say()  { printf "${C_BLUE}==>${C_RESET} %s\n" "$*"; }
ok()   { printf "${C_GREEN}ok${C_RESET}   %s\n" "$*"; }
warn() { printf "${C_YELLOW}warn${C_RESET} %s\n" "$*" >&2; }
fail() { printf "${C_RED}fail${C_RESET} %s\n" "$*" >&2; exit 1; }

# ----- Arg parsing -----------------------------------------------------------
ACTION="apply"
for arg in "$@"; do
  case "$arg" in
    --reset)  ACTION="reset" ;;
    --status) ACTION="status" ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# //; s/^#$//'
      exit 0
      ;;
    *) fail "unknown arg: ${arg} (try --help)" ;;
  esac
done

# ----- Locate tailscale CLI --------------------------------------------------
TS_BIN="${TAILSCALE_CLI:-}"
if [[ -z "${TS_BIN}" ]]; then
  if command -v tailscale >/dev/null 2>&1; then
    TS_BIN="$(command -v tailscale)"
  elif [[ -x "/mnt/c/Program Files/Tailscale/tailscale.exe" ]]; then
    # Windows host install; from WSL we reach it via /mnt/c.
    TS_BIN="/mnt/c/Program Files/Tailscale/tailscale.exe"
  else
    fail "tailscale CLI not found on PATH and Windows Tailscale not detected.
  Install the CLI in WSL  (curl -fsSL https://tailscale.com/install.sh | sh)
  OR export TAILSCALE_CLI=/mnt/c/Program\\ Files/Tailscale/tailscale.exe"
  fi
fi
say "Using tailscale CLI: ${TS_BIN}"

# ----- Preflight: daemon login, cert availability ---------------------------
preflight() {
  say "Checking tailscale status..."
  if ! "${TS_BIN}" status >/dev/null 2>&1; then
    fail "tailscaled is not running or not logged in.
  Start + log in first:
    sudo tailscale up            # WSL install
    or in Windows Tailscale tray: Sign in
  Then re-run this script."
  fi

  local backend
  backend="$("${TS_BIN}" status --json 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("BackendState","?"))' 2>/dev/null || echo "?")"
  if [[ "${backend}" != "Running" ]]; then
    fail "Tailscale BackendState=${backend} (expected Running). Sign in and retry."
  fi
  ok "tailscale daemon is Running"

  say "Checking HTTPS cert for ${TAILNET_HOST} (provisioned by LetsEncrypt via Tailscale)..."
  # `tailscale cert` without args lists/issues the node cert. It returns 0 if
  # a cert is available (and caches it for tailscaled). Non-zero means HTTPS
  # is not yet enabled on the tailnet — fix in the admin console under DNS >
  # HTTPS certificates.
  if ! "${TS_BIN}" cert "${TAILNET_HOST}" >/dev/null 2>&1; then
    warn "tailscale cert failed for ${TAILNET_HOST}. HTTPS may not be enabled on the tailnet,
       or MagicDNS is disabled. Open https://login.tailscale.com/admin/dns and:
         1. Enable MagicDNS
         2. Enable HTTPS Certificates
       Then re-run this script. Proceeding anyway — set-config will still apply,
       but the initial request may 502 until the cert is cached."
  else
    ok "HTTPS cert is available"
  fi
}

# ----- Apply serve config (idempotent) --------------------------------------
apply_config() {
  [[ -f "${CONFIG_FILE}" ]] || fail "Config file missing: ${CONFIG_FILE}"
  say "Applying serve-config from ${CONFIG_FILE}"

  # Preferred path (tailscale 1.56+): `tailscale serve set-config <file>`.
  # Fall back to the legacy `tailscale set --serve-config=...` form if the
  # installed CLI is older.
  if "${TS_BIN}" serve --help 2>&1 | grep -q 'set-config'; then
    "${TS_BIN}" serve set-config "${CONFIG_FILE}"
  elif "${TS_BIN}" set --help 2>&1 | grep -q -- '--serve-config'; then
    "${TS_BIN}" set --serve-config="${CONFIG_FILE}"
  else
    fail "Installed CLI does not support either 'tailscale serve set-config <file>'
  nor 'tailscale set --serve-config=<file>'. Upgrade tailscale (>=1.56)."
  fi
  ok "serve config applied"

  # The config JSON includes AllowFunnel:true on the three public hosts, which
  # is sufficient to enable funnel — no extra CLI invocation is strictly
  # needed. But to be belt-and-braces (and to catch CLI versions that ignore
  # the AllowFunnel block), we also explicitly toggle funnel --bg on each
  # public host:port, which idempotently re-writes the same entry.
  #
  # Note: `tailscale funnel --bg <port>` with no host arg toggles funnel
  # for THIS node's tailnet hostname at that port. For multi-host routing
  # the authoritative config is AllowFunnel in set-config. The CLI funnel
  # subcommand is used here only as a smoke test — if it errors we log it
  # but don't abort, because set-config already committed the intent.
  say "Requesting funnel on port 443 (background, persistent)"
  if "${TS_BIN}" funnel --help 2>&1 | grep -q -- '--bg'; then
    if ! "${TS_BIN}" funnel --bg 443 >/tmp/funnel-bg.out 2>&1; then
      warn "tailscale funnel --bg 443 returned non-zero; check /tmp/funnel-bg.out.
       This is usually benign when set-config already enabled funnel via AllowFunnel."
    else
      ok "funnel --bg 443 accepted"
    fi
  else
    warn "tailscale funnel CLI has no --bg flag; relying on AllowFunnel in set-config."
  fi
}

# ----- Status --------------------------------------------------------------
show_status() {
  say "tailscale serve status:"
  "${TS_BIN}" serve status || true
  echo
  say "tailscale funnel status:"
  "${TS_BIN}" funnel status || true
  echo
  say "Exported serve-config (huJSON):"
  "${TS_BIN}" serve get-config 2>/dev/null | head -80 || true
}

# ----- Smoke test ----------------------------------------------------------
smoke_test() {
  say "Smoke testing public URLs (HEAD, follow redirects, 10s timeout)..."
  for host in "${PUBLIC_HOSTS[@]}"; do
    local url="https://${host}"
    if curl -sS -I -L --max-time 10 -o /dev/null -w "  %{http_code}  ${url}\n" "${url}"; then
      :
    else
      warn "curl failed for ${url} — could be DNS propagation delay or cert not yet provisioned."
    fi
  done
  echo
  say "Tailnet-only smoke (must be run FROM a tailnet device; will fail from the open internet):"
  curl -sS -I --max-time 5 "https://${TAILNET_HOST}/health" \
    -o /dev/null -w "  %{http_code}  https://${TAILNET_HOST}/health\n" || \
    warn "not reachable (expected from non-tailnet hosts)"
}

# ----- Reset ---------------------------------------------------------------
reset_all() {
  say "Resetting tailscale funnel + serve (daemon stays up)..."
  "${TS_BIN}" funnel reset || warn "funnel reset returned non-zero (maybe nothing to reset)"
  "${TS_BIN}" serve reset  || warn "serve reset returned non-zero (maybe nothing to reset)"
  ok "tailscale serve + funnel cleared. The daemon is still logged in."
}

# ----- Main ---------------------------------------------------------------
main() {
  case "${ACTION}" in
    status)
      preflight
      show_status
      ;;
    reset)
      preflight
      reset_all
      ;;
    apply)
      preflight
      apply_config
      echo
      show_status
      echo
      smoke_test
      echo
      printf "${C_BOLD}Public URLs:${C_RESET}\n"
      for host in "${PUBLIC_HOSTS[@]}"; do
        printf "  https://%s/\n" "${host}"
      done
      printf "\n${C_BOLD}Tailnet-only URLs:${C_RESET}\n"
      printf "  https://%s/  (and https://<id>.%s/)\n" "${TAILNET_HOST}" "${TAILNET_HOST}"
      printf "\n${C_BOLD}Rollback:${C_RESET}  %s --reset\n" "$0"
      ;;
    *) fail "unknown ACTION=${ACTION}" ;;
  esac
}

main
