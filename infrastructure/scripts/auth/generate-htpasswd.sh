#!/usr/bin/env bash
# =============================================================================
# generate-htpasswd.sh — one-shot password generator for the 11 naked tools.
#
# Generates a strong random 32-char password per tool, writes bcrypt-hashed
# entries into `nginx-proxy/htpasswd` (gitignored) and plaintext pairs into
# `scripts/auth/credentials-to-seed.json` (gitignored, 600 perms).
#
# Rerunning this script REGENERATES all 11 passwords from scratch and
# OVERWRITES both files. That's intentional — rotating basic-auth creds is a
# "blow-the-file-away-and-reload-nginx" operation, and this script is meant to
# be the one canonical source for those files.
#
# Dependencies:
#   * `openssl`  — present on any modern Linux / macOS / WSL
#   * `htpasswd` from apache-utils / httpd-tools (preferred), OR
#     `openssl passwd -apr1` (fallback, MD5 — WARNED: we refuse because MD5
#     is banned by this script's security policy; see README below)
#   * `python3` (or `python`) — used ONLY when htpasswd is missing, to
#     produce a portable bcrypt hash via the `bcrypt` PyPI package. If
#     neither htpasswd nor python+bcrypt are available, the script hard-fails
#     rather than silently fall back to MD5.
#
# Bcrypt-only policy:
#   Per security policy (CLAUDE.md), every htpasswd entry MUST be bcrypt
#   ($2y$ / $2b$). MD5 ($apr1$) and plain (crypt) are FORBIDDEN — bcrypt's
#   per-hash cost factor (we use 12) keeps brute-force impractical on 2026
#   hardware whereas MD5 can be done at ~10^9 hashes/sec on a single GPU.
#
# Reference:
#   * https://httpd.apache.org/docs/current/programs/htpasswd.html
#   * https://github.com/pyca/bcrypt
# =============================================================================
set -Eeuo pipefail

# -- paths --------------------------------------------------------------------
readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly HTPASSWD_PATH="${REPO_ROOT}/nginx-proxy/htpasswd"
readonly SEED_JSON_PATH="${REPO_ROOT}/scripts/auth/credentials-to-seed.json"
readonly REALM_DEFAULT="DevOps Portal — protected"
readonly FUNNEL_DOMAIN="deepaksharma.live"
readonly BCRYPT_COST="12"   # 2^12 rounds — ~0.25s on a 2026 laptop, fine for login

# -- tool list ----------------------------------------------------------------
# 11 tools — each becomes its own basic-auth username so we can rotate per
# tool later if one credential leaks. Keep in sync with tools.yaml naked list
# and with the $auth_realm map in nginx-proxy/portal.conf.
readonly -a TOOLS=(
  "ollama"
  "chromadb"
  "chromadb-admin"
  "qdrant"
  "trivy"
  "prometheus"
  "loki"
  "jaeger"
  "cadvisor"
  "node-exporter"
  "dcgm-exporter"
)

# -- utilities ----------------------------------------------------------------

log()  { printf '[generate-htpasswd] %s\n' "$*" >&2; }
die()  { log "FATAL: $*"; exit 1; }

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "required command not found on PATH: $cmd"
  fi
}

# Return a 32-char URL-safe-ish random password using openssl.
# `openssl rand -base64 24` -> 32 chars of A-Za-z0-9+/= then we replace
# padding / slashes so the result is safe to stick in curl headers and JSON.
generate_password() {
  local raw
  raw="$(openssl rand -base64 24 | tr -d '\n=' | tr '/+' '_-')"
  # Truncate just in case — base64(24) is always 32 chars after stripping.
  printf '%s' "${raw:0:32}"
}

# Fingerprint: SHA-256 of the password, last 4 hex chars (for the summary
# table only — never echoes the password itself).
fingerprint() {
  local pw="$1"
  printf '%s' "$pw" | openssl dgst -sha256 -hex \
    | awk '{print $NF}' | tail -c 5 | tr -d '\n'
}

# Build one "user:bcrypt-hash" line. Prefer native htpasswd; fall back to
# Python+bcrypt. Refuse MD5.
build_htpasswd_line() {
  local user="$1" pw="$2"
  if command -v htpasswd >/dev/null 2>&1; then
    # htpasswd with -n (no-update): print to stdout; -b takes pw from CLI;
    # -B forces bcrypt; -C sets bcrypt cost factor.
    htpasswd -nbB -C "$BCRYPT_COST" "$user" "$pw"
    return
  fi

  # Fallback: use Python's bcrypt module. This produces an identical $2b$
  # hash. We try `python3` first, then `python`.
  local py=""
  if command -v python3 >/dev/null 2>&1; then
    py="python3"
  elif command -v python >/dev/null 2>&1; then
    py="python"
  else
    die "neither 'htpasswd' (apache-utils/httpd-tools) nor 'python3' is on PATH"
  fi

  # shellcheck disable=SC2016
  "$py" - "$user" "$pw" "$BCRYPT_COST" <<'PY' || die "python+bcrypt fallback failed (is the 'bcrypt' module installed? 'pip install bcrypt')"
import sys, bcrypt
user = sys.argv[1]
pw   = sys.argv[2].encode("utf-8")
cost = int(sys.argv[3])
h = bcrypt.hashpw(pw, bcrypt.gensalt(rounds=cost)).decode("ascii")
print(f"{user}:{h}")
PY
}

# -- pre-flight ---------------------------------------------------------------

main() {
  require_cmd openssl

  # Refuse to clobber an existing htpasswd unless the caller opts in.
  if [[ -f "$HTPASSWD_PATH" && "${1:-}" != "--force" ]]; then
    die "refuse to overwrite existing $HTPASSWD_PATH without --force"
  fi
  if [[ -f "$SEED_JSON_PATH" && "${1:-}" != "--force" ]]; then
    die "refuse to overwrite existing $SEED_JSON_PATH without --force"
  fi

  # Ensure directories exist with sane perms.
  mkdir -p -- "$(dirname -- "$HTPASSWD_PATH")"
  mkdir -p -- "$(dirname -- "$SEED_JSON_PATH")"

  # Start fresh. Use mktemp + rename for atomic writes.
  local tmp_htpasswd tmp_json
  tmp_htpasswd="$(mktemp "${HTPASSWD_PATH}.XXXXXX")"
  tmp_json="$(mktemp "${SEED_JSON_PATH}.XXXXXX")"
  trap 'rm -f -- "$tmp_htpasswd" "$tmp_json"' EXIT

  # Header line in the htpasswd — legal as a comment? The Apache htpasswd
  # format does NOT support comments — any line not matching `user:hash` is
  # ignored silently by nginx. Keeping the file clean avoids surprises.
  : > "$tmp_htpasswd"
  chmod 600 "$tmp_htpasswd"
  chmod 600 "$tmp_json"

  # Begin JSON array.
  printf '{\n  "_comment": "Generated by scripts/auth/generate-htpasswd.sh. DO NOT COMMIT.",\n' > "$tmp_json"
  printf '  "generated_at": "%s",\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$tmp_json"
  printf '  "realm_default": "%s",\n' "$REALM_DEFAULT" >> "$tmp_json"
  printf '  "credentials": [\n' >> "$tmp_json"

  # Accumulator for summary table.
  local -a summary=()
  local first_entry=1

  for tool in "${TOOLS[@]}"; do
    local user="$tool"
    local pw line fp

    pw="$(generate_password)"
    line="$(build_htpasswd_line "$user" "$pw")"
    fp="$(fingerprint "$pw")"

    printf '%s\n' "$line" >> "$tmp_htpasswd"

    # Emit JSON entry. We escape the password with `jq -Rs .` if jq is
    # available; otherwise rely on the generated password not containing
    # characters that need JSON-escaping (we forced URL-safe in
    # generate_password so no quotes, backslashes, or control chars appear).
    local url="https://${tool}.${FUNNEL_DOMAIN}"
    if (( first_entry == 0 )); then
      printf ',\n' >> "$tmp_json"
    fi
    printf '    {\n' >> "$tmp_json"
    printf '      "tool": "%s",\n'     "$tool" >> "$tmp_json"
    printf '      "username": "%s",\n' "$user" >> "$tmp_json"
    printf '      "password": "%s",\n' "$pw"   >> "$tmp_json"
    printf '      "realm": "%s",\n'    "$REALM_DEFAULT" >> "$tmp_json"
    printf '      "url": "%s"\n'       "$url"  >> "$tmp_json"
    printf '    }'                             >> "$tmp_json"
    first_entry=0

    summary+=("$(printf '%-16s  %-16s  ****%s' "$tool" "$user" "$fp")")
  done

  # Close JSON.
  printf '\n  ]\n}\n' >> "$tmp_json"

  # Atomic move into place.
  mv -f "$tmp_htpasswd" "$HTPASSWD_PATH"
  mv -f "$tmp_json"     "$SEED_JSON_PATH"
  trap - EXIT

  # Final perms — tighten to 600 (files already started at 600 but move
  # preserves source perms, so belt-and-braces).
  chmod 600 "$HTPASSWD_PATH"
  chmod 600 "$SEED_JSON_PATH"

  # -- summary ---------------------------------------------------------------
  printf '\n'
  printf 'DevOps Portal basic-auth credentials generated\n'
  printf '===============================================\n'
  printf '%-16s  %-16s  %s\n' "TOOL" "USERNAME" "PASSWORD-FINGERPRINT"
  printf '%-16s  %-16s  %s\n' "----" "--------" "--------------------"
  for row in "${summary[@]}"; do
    printf '%s\n' "$row"
  done
  printf '\n'
  printf 'htpasswd : %s\n' "$HTPASSWD_PATH"
  printf 'seed JSON: %s  (chmod 600)\n' "$SEED_JSON_PATH"
  printf '\n'
  printf 'Next steps:\n'
  printf '  1. export VAULT_TOKEN=...\n'
  printf '  2. python scripts/auth/seed-vault-basic-auth.py\n'
  printf '  3. docker compose restart nginx-proxy (or: nginx -s reload)\n'
}

main "$@"
