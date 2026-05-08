#!/usr/bin/env bash
# =============================================================================
# bootstrap-tcp.sh
# -----------------------------------------------------------------------------
# Bring up the "ALL tools public" design:
#
#   Tailscale Funnel :443 (TCP passthrough)
#       -> 127.0.0.1:8443  (host nginx, TLS terminated w/ Let's Encrypt wildcard)
#           -> SNI dispatch to localhost:<tool-port>
#
# This replaces the 3-slot HTTPS design bootstrap (bootstrap-funnel.sh). We
# keep both scripts on disk — use bootstrap-funnel.sh for the old design,
# bootstrap-tcp.sh for this one. Only ONE can be active at a time:
# `tailscale serve set-config` is declarative.
#
# Usage:
#   ./tailscale/bootstrap-tcp.sh --apply    # apply the TCP passthrough config
#   ./tailscale/bootstrap-tcp.sh --status   # show current serve/funnel state
#   ./tailscale/bootstrap-tcp.sh --reset    # tailscale funnel reset && serve reset
#
# Exit codes:
#   0 — success
#   2 — tailscale daemon not running or not logged in
#   3 — wildcard cert missing at /etc/letsencrypt/live/deepaksharma.live/
#   4 — serve config file missing or unparseable
# =============================================================================

set -euo pipefail

# ----- Paths & constants -----------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_TEMPLATE="${SCRIPT_DIR}/serve-config.json"
# We never mutate the template in-place; render to a temp file first.
RENDERED_CONFIG="${TMPDIR:-/tmp}/serve-config.tcp.rendered.json"

# Apex domain for the public cert.
CERT_DOMAIN="deepaksharma.live"
# Where Let's Encrypt stores the wildcard cert on Linux / WSL.
# Verified against https://letsencrypt.org/docs/certbot-which/#where-are-my-certificates
CERT_DIR_DEFAULT="/etc/letsencrypt/live/${CERT_DOMAIN}"
CERT_DIR="${CERT_DIR:-$CERT_DIR_DEFAULT}"

# Subdomains we curl as a smoke test after set-config.
SMOKE_HOSTS=(
  "deepaksharma.live"
  "api.deepaksharma.live"
  "grafana.deepaksharma.live"
)

# ----- Pretty print helpers --------------------------------------------------
C_RESET="\033[0m"; C_BOLD="\033[1m"; C_GREEN="\033[32m"
C_YELLOW="\033[33m"; C_RED="\033[31m"; C_BLUE="\033[34m"

say()  { printf "${C_BLUE}==>${C_RESET} %s\n" "$*"; }
ok()   { printf "${C_GREEN}ok${C_RESET}   %s\n" "$*"; }
warn() { printf "${C_YELLOW}warn${C_RESET} %s\n" "$*" >&2; }
fail() { local code="${2:-1}"; printf "${C_RED}fail${C_RESET} %s\n" "$1" >&2; exit "${code}"; }

# ----- Arg parsing -----------------------------------------------------------
ACTION="apply"
for arg in "$@"; do
  case "$arg" in
    --apply)  ACTION="apply"  ;;
    --reset)  ACTION="reset"  ;;
    --status) ACTION="status" ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# //; s/^#$//'
      exit 0
      ;;
    *) fail "unknown arg: ${arg} (try --help)" 1 ;;
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
  Install the CLI in WSL (curl -fsSL https://tailscale.com/install.sh | sh)
  OR export TAILSCALE_CLI=/mnt/c/Program\\ Files/Tailscale/tailscale.exe" 2
  fi
fi
say "Using tailscale CLI: ${TS_BIN}"

# ----- Preflight: daemon login + cert availability --------------------------
preflight() {
  say "Checking tailscale status..."
  if ! "${TS_BIN}" status >/dev/null 2>&1; then
    fail "tailscaled is not running or not logged in.
  Start + log in first:
    sudo tailscale up                  # WSL install
    or in Windows Tailscale tray: Sign in
  Then re-run this script." 2
  fi

  # Parse BackendState from tailscale status --json. Uses python3 for
  # portability (jq may not be installed everywhere).
  local backend
  backend="$("${TS_BIN}" status --json 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("BackendState","?"))' \
    2>/dev/null || echo "?")"
  if [[ "${backend}" != "Running" ]]; then
    fail "Tailscale BackendState=${backend} (expected Running). Sign in and retry." 2
  fi
  ok "tailscale daemon is Running"
}

# ----- Derive MagicDNS name from the local node ------------------------------
# Syntax verified: `tailscale status --json | jq -r .Self.DNSName` documented
# at https://tailscale.com/s/status-json (Self.DNSName is FQDN with trailing dot).
get_magic_dns() {
  "${TS_BIN}" status --json \
    | python3 -c 'import sys,json
data=json.load(sys.stdin)
name=(data.get("Self") or {}).get("DNSName","")
print(name.rstrip("."))'
}

# ----- Check for the wildcard cert ------------------------------------------
# Runs on the host that will run nginx. If the cert isn't on disk yet, tell
# the user what to do. Does NOT try to issue it — that's out of scope here.
cert_preflight() {
  say "Checking for Let's Encrypt wildcard cert in ${CERT_DIR} ..."
  if [[ ! -f "${CERT_DIR}/fullchain.pem" || ! -f "${CERT_DIR}/privkey.pem" ]]; then
    warn "wildcard cert NOT found at ${CERT_DIR}/{fullchain,privkey}.pem
  See docs/PUBLIC_ACCESS_DEEPAKSHARMA_LIVE.md §Phase B for certbot DNS-01 setup.
  Shortest path (Cloudflare DNS):
    sudo certbot certonly --dns-cloudflare \\
      --dns-cloudflare-credentials ~/.secrets/certbot/cloudflare.ini \\
      --preferred-challenges dns \\
      -d '*.${CERT_DOMAIN}' -d '${CERT_DOMAIN}' \\
      --agree-tos --email deepakdce2009@gmail.com
  Proceeding anyway — nginx will fail to start until the cert is present."
    # Not exiting: the user may supply the cert via a docker volume mount
    # and certbot might live elsewhere. But DO surface the severity.
    return 3
  fi
  ok "wildcard cert found"
  return 0
}

# ----- Render serve-config.json with ${MAGIC_DNS_NAME} substituted ----------
render_config() {
  [[ -f "${CONFIG_TEMPLATE}" ]] || fail "template missing: ${CONFIG_TEMPLATE}" 4
  local magic_dns
  magic_dns="$(get_magic_dns)"
  if [[ -z "${magic_dns}" ]]; then
    fail "could not derive MagicDNS name from 'tailscale status --json'. Is MagicDNS enabled in https://login.tailscale.com/admin/dns ?" 2
  fi
  say "MagicDNS name: ${magic_dns}"

  # Substitute placeholder. Use sed since the template is huJSON; python
  # would require a huJSON parser (tailscale ships one, we don't).
  sed "s|\${MAGIC_DNS_NAME}|${magic_dns}|g" \
    "${CONFIG_TEMPLATE}" > "${RENDERED_CONFIG}"

  # Verify the rendered file is still huJSON-valid by round-tripping through
  # python json (after stripping comments/trailing commas).
  if ! python3 - "${RENDERED_CONFIG}" <<'PY'
import re, sys, json
p = sys.argv[1]
raw = open(p).read()
# strip // and /* */ comments
stripped = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
stripped = re.sub(r'//[^\n]*', '', stripped)
# strip trailing commas
stripped = re.sub(r',(\s*[\]}])', r'\1', stripped)
try:
    json.loads(stripped)
except Exception as e:
    print(f'rendered serve-config parse error: {e}', file=sys.stderr)
    sys.exit(1)
PY
  then
    fail "rendered serve-config is not valid huJSON; see ${RENDERED_CONFIG}" 4
  fi

  ok "rendered to ${RENDERED_CONFIG}"
}

# ----- Apply serve config + enable funnel -----------------------------------
apply_config() {
  render_config
  say "Applying serve-config (TCP passthrough) ..."

  # Preferred path (tailscale 1.56+): `tailscale serve set-config <file>`.
  # Docs: https://tailscale.com/kb/1242/tailscale-serve#saving-configurations
  if "${TS_BIN}" serve --help 2>&1 | grep -q 'set-config'; then
    "${TS_BIN}" serve set-config "${RENDERED_CONFIG}"
  elif "${TS_BIN}" set --help 2>&1 | grep -q -- '--serve-config'; then
    "${TS_BIN}" set --serve-config="${RENDERED_CONFIG}"
  else
    fail "installed tailscale CLI supports neither 'serve set-config' nor 'set --serve-config'. Upgrade to 1.56+." 4
  fi
  ok "serve config applied"

  # Explicit funnel toggle. In TCP-passthrough mode, `tailscale funnel --bg 443`
  # adds the MagicDNS:443 tuple to AllowFunnel. Verified in
  # https://tailscale.com/kb/1223/funnel-availability and `tailscale funnel -h`.
  #
  # Flag note: `--bg` was introduced in tailscale 1.58 (github release notes).
  # If the CLI is older, set-config's AllowFunnel block already committed the
  # intent, so this is a belt-and-braces.
  say "Enabling funnel on :443 (background) ..."
  if "${TS_BIN}" funnel --help 2>&1 | grep -q -- '--bg'; then
    "${TS_BIN}" funnel --bg 443 || warn "funnel --bg 443 returned non-zero — usually benign when set-config committed."
  else
    warn "tailscale funnel has no --bg flag; relying on AllowFunnel in set-config."
  fi
}

# ----- Status ---------------------------------------------------------------
show_status() {
  say "tailscale status (summary):"
  "${TS_BIN}" status || true
  echo
  say "tailscale serve status:"
  "${TS_BIN}" serve status || true
  echo
  say "tailscale funnel status:"
  "${TS_BIN}" funnel status || true
  echo
  say "AllowFunnel entries in running config:"
  "${TS_BIN}" serve get-config 2>/dev/null \
    | python3 -c 'import re,sys,json
raw=sys.stdin.read()
s=re.sub(r"/\*.*?\*/","",raw,flags=re.S)
s=re.sub(r"//[^\n]*","",s)
s=re.sub(r",(\s*[\]}])",r"\1",s)
try:
  d=json.loads(s)
except Exception as e:
  print("<parse err:",e,">"); sys.exit(0)
for k,v in (d.get("AllowFunnel") or {}).items():
  print(f"  {k}  ->  {v}")' \
    || warn "serve get-config unavailable"
}

# ----- Smoke test -----------------------------------------------------------
smoke_test() {
  say "Smoke testing ${#SMOKE_HOSTS[@]} sample hostnames ..."
  # We have to test via the real DNS for each host; if the DNS isn't set up
  # yet, fall back to --resolve spoofing the public DNS to the funnel's
  # tailnet endpoint. That only works if you're on the tailnet already.
  local magic_dns
  magic_dns="$(get_magic_dns)"
  for host in "${SMOKE_HOSTS[@]}"; do
    local url="https://${host}/"
    if curl -sS -I -L --max-time 10 -o /dev/null -w "  %{http_code}  ${url}\n" "${url}"; then
      :
    else
      warn "curl failed for ${url} — DNS may not have propagated, or cert mismatch."
    fi
  done

  say "Tailnet-side smoke (from this host; should succeed once set-config applies):"
  curl -sS -I --max-time 5 "https://${magic_dns}/" \
    -o /dev/null -w "  %{http_code}  https://${magic_dns}/\n" \
    || warn "tailnet-side curl failed — check tailscale serve status."
}

# ----- Reset ---------------------------------------------------------------
reset_all() {
  say "Resetting tailscale funnel + serve (daemon stays up)..."
  "${TS_BIN}" funnel reset || warn "funnel reset returned non-zero (maybe nothing to reset)"
  "${TS_BIN}" serve reset  || warn "serve reset  returned non-zero (maybe nothing to reset)"
  # Also remove the rendered artefact to avoid stale state on next run.
  rm -f "${RENDERED_CONFIG}"
  ok "tailscale serve + funnel cleared. Daemon is still logged in."
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
      cert_preflight || warn "proceeding without cert — nginx will fail until cert is in place"
      apply_config
      echo
      show_status
      echo
      smoke_test
      echo
      printf "${C_BOLD}Public URLs (all 28 tools):${C_RESET} see tools.yaml .url_funnel field\n"
      printf "${C_BOLD}Rollback:${C_RESET}  %s --reset\n" "$0"
      ;;
    *) fail "unknown ACTION=${ACTION}" 1 ;;
  esac
}

main
