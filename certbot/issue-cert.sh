#!/usr/bin/env bash
# =============================================================================
# issue-cert.sh — one-shot wildcard-cert issuance for *.deepaksharma.live.
# -----------------------------------------------------------------------------
# Orchestrates:
#   1. Pre-flight: validates secrets, perms, docker availability, DNS provider.
#   2. Runs certbot certonly (Cloudflare by default; --provider=route53 for R53).
#   3. Mirrors live/<cert>/{fullchain,privkey}.pem to nginx-proxy/certs/.
#   4. Best-effort reload of the nginx-proxy container (warns on miss).
#
# Usage:
#   ./issue-cert.sh                      # Cloudflare, PROD Let's Encrypt
#   ./issue-cert.sh --dry-run            # Cloudflare, STAGING (untrusted cert)
#   ./issue-cert.sh --provider=route53   # Route53, PROD
#   ./issue-cert.sh --provider=route53 --dry-run
#
# Runs inside Git Bash on Windows (forward-slash paths everywhere).
# =============================================================================

set -Eeuo pipefail
IFS=$'\n\t'

# --- locate repo root relative to this script ---------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CERTBOT_DIR="$SCRIPT_DIR"
NGINX_CERTS_DIR="$REPO_ROOT/nginx-proxy/certs"

# --- defaults -----------------------------------------------------------------
PROVIDER="cloudflare"
DRY_RUN=0
DOMAIN="deepaksharma.live"

# --- colour helpers -----------------------------------------------------------
if [[ -t 1 ]]; then
    C_RED=$'\e[31m'; C_GRN=$'\e[32m'; C_YEL=$'\e[33m'
    C_BLU=$'\e[34m'; C_RST=$'\e[0m'
else
    C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_RST=""
fi
info()  { printf "%s[INFO]%s  %s\n" "$C_BLU" "$C_RST" "$*"; }
warn()  { printf "%s[WARN]%s  %s\n" "$C_YEL" "$C_RST" "$*" >&2; }
error() { printf "%s[ERR ]%s  %s\n" "$C_RED" "$C_RST" "$*" >&2; }
ok()    { printf "%s[ OK ]%s  %s\n" "$C_GRN" "$C_RST" "$*"; }

# --- argument parse -----------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --provider=*)  PROVIDER="${arg#*=}" ;;
        --dry-run)     DRY_RUN=1 ;;
        --domain=*)    DOMAIN="${arg#*=}" ;;
        -h|--help)
            grep -E '^# ' "${BASH_SOURCE[0]}" | head -40
            exit 0
            ;;
        *) error "Unknown argument: $arg"; exit 2 ;;
    esac
done

info "Certbot issuance starting"
info "  provider : $PROVIDER"
info "  domain   : $DOMAIN (+ *.${DOMAIN})"
info "  mode     : $([[ $DRY_RUN == 1 ]] && echo STAGING || echo PROD)"
info "  repo     : $REPO_ROOT"

# --- pick compose file + service per provider --------------------------------
case "$PROVIDER" in
    cloudflare)
        COMPOSE_FILE="$CERTBOT_DIR/docker-compose.certbot.yml"
        SERVICE="certbot"
        SERVICE_STAGING="certbot-staging"
        SECRET_FILE="$CERTBOT_DIR/secrets/cloudflare.ini"
        ;;
    route53)
        COMPOSE_FILE="$CERTBOT_DIR/docker-compose.route53.yml"
        SERVICE="certbot-r53"
        SERVICE_STAGING="certbot-r53-staging"
        SECRET_FILE="$CERTBOT_DIR/secrets/route53.env"
        ;;
    *)
        error "Unknown provider '$PROVIDER'. Use: cloudflare | route53"
        exit 2
        ;;
esac

# --- pre-flight checks --------------------------------------------------------
preflight() {
    # docker
    if ! command -v docker >/dev/null 2>&1; then
        error "docker CLI not found on PATH"
        exit 3
    fi
    # Workaround for the DOCKER_HOST gotcha in Git Bash (documented in MEMORY).
    unset DOCKER_HOST || true
    export DOCKER_CONTEXT="${DOCKER_CONTEXT:-desktop-linux}"
    if ! docker info >/dev/null 2>&1; then
        error "docker engine unreachable (context=$DOCKER_CONTEXT). Start Docker Desktop and retry."
        exit 3
    fi

    # compose
    if ! docker compose version >/dev/null 2>&1; then
        error "docker compose v2 plugin missing"
        exit 3
    fi

    # compose file
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        error "compose file not found: $COMPOSE_FILE"
        exit 3
    fi

    # secret file
    if [[ ! -f "$SECRET_FILE" ]]; then
        error "credentials file missing: $SECRET_FILE"
        error "  template exists at: ${SECRET_FILE}.example"
        error "  copy it, fill in the token, then: chmod 600 $SECRET_FILE"
        exit 4
    fi

    # perms — must be 600 (or 400). anything broader leaks the token to every
    # user on the box.
    local perms
    # stat -c on Linux/GNU; Git Bash ships GNU coreutils.
    perms="$(stat -c '%a' "$SECRET_FILE" 2>/dev/null || stat -f '%Lp' "$SECRET_FILE" 2>/dev/null || echo "")"
    if [[ -z "$perms" ]]; then
        warn "could not stat $SECRET_FILE (continuing, but verify perms manually)"
    elif [[ "$perms" != "600" && "$perms" != "400" ]]; then
        error "$SECRET_FILE has permissions $perms (expected 600 or 400)"
        error "  fix: chmod 600 $SECRET_FILE"
        exit 4
    fi

    # token placeholder check (common operator mistake: forgot to edit the file)
    if grep -q 'REPLACE_WITH_' "$SECRET_FILE"; then
        error "$SECRET_FILE still contains a REPLACE_WITH_ placeholder — edit it first"
        exit 4
    fi

    ok "pre-flight checks passed"
}

preflight

# --- run certbot --------------------------------------------------------------
cd "$CERTBOT_DIR"
mkdir -p "$CERTBOT_DIR/letsencrypt" "$CERTBOT_DIR/logs"

if [[ $DRY_RUN == 1 ]]; then
    TARGET_SERVICE="$SERVICE_STAGING"
    info "Running STAGING issuance (output cert will NOT be trusted by browsers)"
else
    TARGET_SERVICE="$SERVICE"
    info "Running PROD issuance against Let's Encrypt production API"
fi

info "docker compose -f $COMPOSE_FILE run --rm $TARGET_SERVICE"

if ! docker compose -f "$COMPOSE_FILE" run --rm "$TARGET_SERVICE"; then
    error "certbot run failed. Check logs above and in $CERTBOT_DIR/logs/"
    exit 5
fi

ok "certbot run completed"

# --- mirror certs to nginx-proxy/certs ---------------------------------------
# Name of the cert lineage varies between PROD and STAGING.
if [[ $DRY_RUN == 1 ]]; then
    CERT_LINEAGE="${DOMAIN}-staging"
else
    CERT_LINEAGE="$DOMAIN"
fi

LIVE_DIR="$CERTBOT_DIR/letsencrypt/live/$CERT_LINEAGE"

if [[ ! -d "$LIVE_DIR" ]]; then
    error "expected cert lineage not found: $LIVE_DIR"
    error "  this usually means certbot hit a propagation or rate-limit error"
    exit 6
fi

mkdir -p "$NGINX_CERTS_DIR"

# Copy (don't symlink) — nginx in a container can't dereference host symlinks
# that point back into /etc/letsencrypt via a separate mount.
cp -f "$LIVE_DIR/fullchain.pem" "$NGINX_CERTS_DIR/fullchain.pem"
cp -f "$LIVE_DIR/privkey.pem"   "$NGINX_CERTS_DIR/privkey.pem"
chmod 644 "$NGINX_CERTS_DIR/fullchain.pem"
chmod 600 "$NGINX_CERTS_DIR/privkey.pem"

ok "mirrored cert to $NGINX_CERTS_DIR"

# --- verify the cert ---------------------------------------------------------
if command -v openssl >/dev/null 2>&1; then
    info "Cert summary:"
    openssl x509 -in "$NGINX_CERTS_DIR/fullchain.pem" -noout \
        -subject -issuer -dates 2>/dev/null | sed 's/^/    /'
    info "Subject Alternative Names:"
    openssl x509 -in "$NGINX_CERTS_DIR/fullchain.pem" -noout -text 2>/dev/null \
        | grep -E 'DNS:' | sed 's/^/    /'
else
    warn "openssl not on PATH — skipping cert introspection"
fi

# --- reload nginx-proxy (best-effort) ----------------------------------------
if docker ps --format '{{.Names}}' | grep -qw nginx-proxy; then
    if docker exec nginx-proxy nginx -t >/dev/null 2>&1; then
        docker exec nginx-proxy nginx -s reload && ok "reloaded nginx-proxy"
    else
        warn "nginx -t failed inside nginx-proxy; not reloading. Inspect with:"
        warn "  docker exec nginx-proxy nginx -t"
    fi
else
    warn "nginx-proxy container not running; skip reload. Start it with:"
    warn "  docker compose -f devops-tools-backend/docker-compose.yml up -d nginx-proxy"
fi

ok "issuance complete"
if [[ $DRY_RUN == 1 ]]; then
    warn "This was STAGING — the cert is UNTRUSTED. Re-run without --dry-run for production."
fi
