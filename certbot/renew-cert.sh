#!/usr/bin/env bash
# =============================================================================
# renew-cert.sh — idempotent cert renewal. Safe to run daily from cron / Task
# Scheduler. Certbot itself only renews lineages with <30 days left, so
# running this hourly would still be a no-op outside the renewal window.
#
# Flow:
#   1. Pre-flight: docker + secrets + compose file.
#   2. `certbot renew` inside the compose service.
#   3. If ANY lineage was renewed, mirror new fullchain/privkey to
#      nginx-proxy/certs/ and reload the nginx-proxy container.
#   4. Log to certbot/logs/renew-YYYYMMDD.log (one log per run).
#   5. Exit 0 if "not due" (no action required) — caller cron should treat
#      this as success, NOT as an error.
#
# Usage:
#   ./renew-cert.sh                    # default: cloudflare
#   ./renew-cert.sh --provider=route53
#   ./renew-cert.sh --force            # passes --force-renewal to certbot
#                                      # (USE SPARINGLY — burns rate limit)
# =============================================================================

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CERTBOT_DIR="$SCRIPT_DIR"
NGINX_CERTS_DIR="$REPO_ROOT/nginx-proxy/certs"
LOG_DIR="$CERTBOT_DIR/logs"
DATE_STR="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/renew-${DATE_STR}.log"

PROVIDER="cloudflare"
FORCE=0
DOMAIN="deepaksharma.live"

for arg in "$@"; do
    case "$arg" in
        --provider=*) PROVIDER="${arg#*=}" ;;
        --force)      FORCE=1 ;;
        --domain=*)   DOMAIN="${arg#*=}" ;;
        -h|--help)
            grep -E '^# ' "${BASH_SOURCE[0]}" | head -30
            exit 0
            ;;
        *)
            echo "[ERR] unknown arg: $arg" >&2
            exit 2
            ;;
    esac
done

mkdir -p "$LOG_DIR"

# Tee everything to the log file from here on so cron captures a full trace.
exec > >(tee -a "$LOG_FILE") 2>&1

echo "================================================================"
echo " renew-cert.sh start  $(date -Iseconds)"
echo "   provider: $PROVIDER   force: $FORCE   domain: $DOMAIN"
echo "   log:      $LOG_FILE"
echo "================================================================"

# pick compose file + service
case "$PROVIDER" in
    cloudflare)
        COMPOSE_FILE="$CERTBOT_DIR/docker-compose.certbot.yml"
        SERVICE="certbot-renew"
        SECRET_FILE="$CERTBOT_DIR/secrets/cloudflare.ini"
        ;;
    route53)
        COMPOSE_FILE="$CERTBOT_DIR/docker-compose.route53.yml"
        SERVICE="certbot-r53-renew"
        SECRET_FILE="$CERTBOT_DIR/secrets/route53.env"
        ;;
    *)
        echo "[ERR] unknown provider '$PROVIDER'"; exit 2 ;;
esac

# pre-flight
if ! command -v docker >/dev/null 2>&1; then
    echo "[ERR] docker CLI not found"; exit 3
fi
unset DOCKER_HOST || true
export DOCKER_CONTEXT="${DOCKER_CONTEXT:-desktop-linux}"
if ! docker info >/dev/null 2>&1; then
    echo "[ERR] docker engine unreachable"; exit 3
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "[ERR] compose file missing: $COMPOSE_FILE"; exit 3
fi
if [[ ! -f "$SECRET_FILE" ]]; then
    echo "[ERR] secret missing: $SECRET_FILE"; exit 4
fi

# due-check: certbot's own logic already gates at <30 days, but we short-circuit
# by inspecting the expiry date so cron sees a fast "not due" path.
LIVE_CERT="$CERTBOT_DIR/letsencrypt/live/$DOMAIN/fullchain.pem"
if [[ -f "$LIVE_CERT" && $FORCE -eq 0 ]] && command -v openssl >/dev/null 2>&1; then
    END_EPOCH="$(openssl x509 -in "$LIVE_CERT" -noout -enddate 2>/dev/null | sed 's/notAfter=//' | xargs -I{} date -d "{}" +%s 2>/dev/null || echo 0)"
    NOW_EPOCH="$(date +%s)"
    if [[ "$END_EPOCH" -gt 0 ]]; then
        DAYS_LEFT=$(( (END_EPOCH - NOW_EPOCH) / 86400 ))
        echo "[INFO] lineage $DOMAIN has $DAYS_LEFT days remaining"
        if [[ "$DAYS_LEFT" -gt 30 ]]; then
            echo "[OK]  not due (>30 days remain); exit 0"
            exit 0
        fi
    fi
fi

# run renew
RENEW_CMD=(docker compose -f "$COMPOSE_FILE" run --rm "$SERVICE")
if [[ $FORCE == 1 ]]; then
    # certbot-renew service already hard-codes `renew`; we inject --force-renewal
    # via COMPOSE_COMMAND override.  Simpler: run `certbot` service with custom cmd.
    echo "[INFO] --force: will force-renew regardless of expiry"
    case "$PROVIDER" in
        cloudflare) SVC_FOR_FORCE="certbot" ;;
        route53)    SVC_FOR_FORCE="certbot-r53" ;;
    esac
    RENEW_CMD=(docker compose -f "$COMPOSE_FILE" run --rm
               --entrypoint certbot "$SVC_FOR_FORCE"
               renew --force-renewal --non-interactive
               --dns-${PROVIDER}-propagation-seconds 60)
fi

echo "[INFO] running: ${RENEW_CMD[*]}"
if ! "${RENEW_CMD[@]}"; then
    echo "[ERR] certbot renew failed"; exit 5
fi

# mirror fresh pems
LIVE_DIR="$CERTBOT_DIR/letsencrypt/live/$DOMAIN"
if [[ -f "$LIVE_DIR/fullchain.pem" ]]; then
    mkdir -p "$NGINX_CERTS_DIR"
    cp -f "$LIVE_DIR/fullchain.pem" "$NGINX_CERTS_DIR/fullchain.pem"
    cp -f "$LIVE_DIR/privkey.pem"   "$NGINX_CERTS_DIR/privkey.pem"
    chmod 644 "$NGINX_CERTS_DIR/fullchain.pem"
    chmod 600 "$NGINX_CERTS_DIR/privkey.pem"
    echo "[OK]  mirrored to $NGINX_CERTS_DIR"
else
    echo "[WARN] no fresh lineage at $LIVE_DIR — nothing to mirror"
fi

# nginx reload (best-effort)
if docker ps --format '{{.Names}}' | grep -qw nginx-proxy; then
    if docker exec nginx-proxy nginx -t >/dev/null 2>&1; then
        docker exec nginx-proxy nginx -s reload
        echo "[OK]  reloaded nginx-proxy"
    else
        echo "[WARN] nginx -t failed inside nginx-proxy — config not reloaded"
    fi
else
    echo "[WARN] nginx-proxy container not running — skipping reload"
fi

echo "================================================================"
echo " renew-cert.sh done   $(date -Iseconds)"
echo "================================================================"
