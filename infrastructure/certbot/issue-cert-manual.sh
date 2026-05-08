#!/usr/bin/env bash
# =============================================================================
# issue-cert-manual.sh — MANUAL DNS-01 issuance (no plugin).
# -----------------------------------------------------------------------------
# Use ONLY when the DNS provider has no certbot plugin. Certbot pauses and
# prints TXT records you must create by hand in the provider's UI; it waits
# for you to press Enter, then verifies propagation and completes issuance.
#
# THIS PATH DOES NOT SUPPORT AUTO-RENEW. Certbot renew will re-prompt for
# manual DNS edits every 60-90 days. If you end up on this path, migrate to
# a plugin-supported provider (see README.md for the supported-plugin list).
#
# Usage:
#   ./issue-cert-manual.sh            # PROD issuance, interactive
#   ./issue-cert-manual.sh --dry-run  # STAGING (untrusted, no rate-limit cost)
# =============================================================================

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CERTBOT_DIR="$SCRIPT_DIR"
NGINX_CERTS_DIR="$REPO_ROOT/nginx-proxy/certs"

DRY_RUN=0
DOMAIN="deepaksharma.live"
EMAIL="${CERTBOT_EMAIL:-deepakdce2009@gmail.com}"

for arg in "$@"; do
    case "$arg" in
        --dry-run)   DRY_RUN=1 ;;
        --domain=*)  DOMAIN="${arg#*=}" ;;
        --email=*)   EMAIL="${arg#*=}" ;;
        -h|--help)
            grep -E '^# ' "${BASH_SOURCE[0]}" | head -25
            exit 0
            ;;
        *) echo "[ERR] unknown arg: $arg" >&2; exit 2 ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "[ERR] docker CLI not found"; exit 3
fi
unset DOCKER_HOST || true
export DOCKER_CONTEXT="${DOCKER_CONTEXT:-desktop-linux}"
if ! docker info >/dev/null 2>&1; then
    echo "[ERR] docker engine unreachable"; exit 3
fi

mkdir -p "$CERTBOT_DIR/letsencrypt" "$CERTBOT_DIR/logs"

cat <<EOF
================================================================
 Manual DNS-01 issuance
   domain:   $DOMAIN (+ *.${DOMAIN})
   email:    $EMAIL
   mode:     $([[ $DRY_RUN == 1 ]] && echo STAGING || echo PROD)
   CWD:      $CERTBOT_DIR

 Certbot will PAUSE and ask you to create TWO TXT records:
     Name:  _acme-challenge.${DOMAIN}
     Type:  TXT
     Value: <printed by certbot>  (one per SAN; the wildcard and apex each
            need their own TXT record with different values)

 STEPS:
   1. When certbot prints the TXT value, log into your DNS provider's UI
      and create the TXT record.
   2. Wait at least 60 seconds for propagation.
      Verify with: dig +short TXT _acme-challenge.${DOMAIN} @8.8.8.8
   3. Press Enter in the certbot prompt.
   4. Repeat for the second SAN (wildcard).
   5. Certbot writes cert under certbot/letsencrypt/live/${DOMAIN}/.
================================================================
EOF

EXTRA_FLAGS=()
CERT_NAME="$DOMAIN"
if [[ $DRY_RUN == 1 ]]; then
    EXTRA_FLAGS+=(--staging)
    CERT_NAME="${DOMAIN}-staging"
fi

# Use base certbot image (no plugin) — interactive -it so prompts flush to TTY.
docker run --rm -it \
    -v "$CERTBOT_DIR/letsencrypt:/etc/letsencrypt" \
    -v "$CERTBOT_DIR/logs:/var/log/letsencrypt" \
    certbot/certbot:v2.11.0 \
    certonly \
    --manual \
    --preferred-challenges dns \
    --agree-tos \
    --email "$EMAIL" \
    -d "*.${DOMAIN}" -d "$DOMAIN" \
    --cert-name "$CERT_NAME" \
    --manual-public-ip-logging-ok \
    "${EXTRA_FLAGS[@]}"

LIVE_DIR="$CERTBOT_DIR/letsencrypt/live/$CERT_NAME"
if [[ -f "$LIVE_DIR/fullchain.pem" ]]; then
    mkdir -p "$NGINX_CERTS_DIR"
    cp -f "$LIVE_DIR/fullchain.pem" "$NGINX_CERTS_DIR/fullchain.pem"
    cp -f "$LIVE_DIR/privkey.pem"   "$NGINX_CERTS_DIR/privkey.pem"
    chmod 644 "$NGINX_CERTS_DIR/fullchain.pem"
    chmod 600 "$NGINX_CERTS_DIR/privkey.pem"
    echo "[OK] mirrored to $NGINX_CERTS_DIR"
else
    echo "[ERR] cert lineage not found at $LIVE_DIR — issuance must have failed"
    exit 6
fi

if docker ps --format '{{.Names}}' | grep -qw nginx-proxy; then
    docker exec nginx-proxy nginx -s reload || echo "[WARN] reload failed"
fi

echo "================================================================"
echo " DONE — MANUAL PATH CANNOT AUTO-RENEW."
echo " Migrate to a plugin-supported DNS provider when possible."
echo "================================================================"
