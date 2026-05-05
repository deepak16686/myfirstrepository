#!/bin/bash
# =============================================================================
# Cloudflare Tunnel Setup — one-time script to expose all infra services
# via *.deepaksharma.live with automatic HTTPS
#
# PREREQUISITES:
#   1. Domain 'deepaksharma.live' added to Cloudflare (free plan)
#   2. GoDaddy nameservers changed to Cloudflare's nameservers
#   3. Cloudflare API token created with these permissions:
#      - Zone:DNS:Edit
#      - Account:Cloudflare Tunnel:Edit
#      - Zone:Zone:Read
#
# USAGE:
#   ./cloudflare-tunnel-setup.sh <CLOUDFLARE_API_TOKEN>
#
# The script will:
#   1. Auto-detect your Account ID and Zone ID
#   2. Create a tunnel named 'devstack'
#   3. Configure all subdomain routes → nginx-proxy:80
#   4. Create DNS CNAME records for every subdomain
#   5. Save the tunnel token to .env for docker-compose
# =============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
DOMAIN="deepaksharma.live"
TUNNEL_NAME="devstack"
ORIGIN_SERVICE="http://nginx-proxy:80"
INFRA_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${INFRA_DIR}/.env"

# All subdomains to expose (must match nginx server_name blocks)
SUBDOMAINS=(
    devstack
    devops-api
    chatbot
    gitlab
    gitea
    jenkins
    sonarqube
    nexus
    vault
    chromadb
    chromadb-admin
    grafana
    prometheus
    minio
    splunk
    jaeger
    cadvisor
    node-exporter
    trivy
    ollama
    qdrant
    jira
    redmine
    loki
)

# ── Validate input ──────────────────────────────────────────────────────────
if [ $# -lt 1 ]; then
    echo "Usage: $0 <CLOUDFLARE_API_TOKEN>"
    echo ""
    echo "Create a token at: https://dash.cloudflare.com/profile/api-tokens"
    echo "Required permissions:"
    echo "  - Zone:DNS:Edit"
    echo "  - Account:Cloudflare Tunnel:Edit"
    echo "  - Zone:Zone:Read"
    exit 1
fi

CF_API_TOKEN="$1"
CF_API="https://api.cloudflare.com/client/v4"

# ── Helper: Cloudflare API call ─────────────────────────────────────────────
cf_api() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"

    if [ -n "$data" ]; then
        curl -s -X "$method" "${CF_API}${endpoint}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "$data"
    else
        curl -s -X "$method" "${CF_API}${endpoint}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json"
    fi
}

# ── Step 1: Verify API token ────────────────────────────────────────────────
echo "=== Step 1: Verifying API token..."
VERIFY=$(cf_api GET "/user/tokens/verify")
if ! echo "$VERIFY" | grep -q '"success":true'; then
    echo "ERROR: Invalid API token. Response:"
    echo "$VERIFY" | python3 -m json.tool 2>/dev/null || echo "$VERIFY"
    exit 1
fi
echo "    Token is valid."

# ── Step 2: Get Account ID ──────────────────────────────────────────────────
echo "=== Step 2: Getting Account ID..."
ACCOUNTS=$(cf_api GET "/accounts?per_page=1")
ACCOUNT_ID=$(echo "$ACCOUNTS" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])" 2>/dev/null)
ACCOUNT_NAME=$(echo "$ACCOUNTS" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['name'])" 2>/dev/null)

if [ -z "$ACCOUNT_ID" ]; then
    echo "ERROR: Could not determine Account ID."
    exit 1
fi
echo "    Account: ${ACCOUNT_NAME} (${ACCOUNT_ID})"

# ── Step 3: Get Zone ID ─────────────────────────────────────────────────────
echo "=== Step 3: Getting Zone ID for ${DOMAIN}..."
ZONES=$(cf_api GET "/zones?name=${DOMAIN}")
ZONE_ID=$(echo "$ZONES" | python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['id'] if r else '')" 2>/dev/null)
ZONE_STATUS=$(echo "$ZONES" | python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['status'] if r else 'not_found')" 2>/dev/null)

if [ -z "$ZONE_ID" ]; then
    echo "ERROR: Domain '${DOMAIN}' not found in Cloudflare."
    echo "       Add it at: https://dash.cloudflare.com → Add a site"
    exit 1
fi
echo "    Zone: ${DOMAIN} (${ZONE_ID}), status: ${ZONE_STATUS}"

if [ "$ZONE_STATUS" != "active" ]; then
    echo ""
    echo "WARNING: Zone status is '${ZONE_STATUS}', not 'active'."
    echo "         Make sure you've updated GoDaddy nameservers to Cloudflare's."
    echo "         It can take up to 24h for nameserver changes to propagate."
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ── Step 4: Create or find tunnel ────────────────────────────────────────────
echo "=== Step 4: Creating tunnel '${TUNNEL_NAME}'..."

# Check if tunnel already exists
EXISTING=$(cf_api GET "/accounts/${ACCOUNT_ID}/cfd_tunnel?name=${TUNNEL_NAME}&is_deleted=false")
EXISTING_ID=$(echo "$EXISTING" | python3 -c "
import sys, json
r = json.load(sys.stdin)['result']
print(r[0]['id'] if r else '')
" 2>/dev/null)

if [ -n "$EXISTING_ID" ]; then
    TUNNEL_ID="$EXISTING_ID"
    echo "    Tunnel already exists: ${TUNNEL_ID}"
else
    # Create new tunnel
    CREATE_RESULT=$(cf_api POST "/accounts/${ACCOUNT_ID}/cfd_tunnel" \
        "{\"name\":\"${TUNNEL_NAME}\",\"tunnel_secret\":\"$(openssl rand -base64 32)\"}")
    TUNNEL_ID=$(echo "$CREATE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['id'])" 2>/dev/null)

    if [ -z "$TUNNEL_ID" ]; then
        echo "ERROR: Failed to create tunnel. Response:"
        echo "$CREATE_RESULT" | python3 -m json.tool 2>/dev/null || echo "$CREATE_RESULT"
        exit 1
    fi
    echo "    Created tunnel: ${TUNNEL_ID}"
fi

# ── Step 5: Get tunnel token ────────────────────────────────────────────────
echo "=== Step 5: Getting tunnel token..."
TOKEN_RESULT=$(cf_api GET "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/token")
TUNNEL_TOKEN=$(echo "$TOKEN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])" 2>/dev/null)

if [ -z "$TUNNEL_TOKEN" ]; then
    echo "ERROR: Failed to get tunnel token. Response:"
    echo "$TOKEN_RESULT" | python3 -m json.tool 2>/dev/null || echo "$TOKEN_RESULT"
    exit 1
fi
echo "    Token retrieved (${#TUNNEL_TOKEN} chars)"

# ── Step 6: Configure tunnel ingress rules ──────────────────────────────────
echo "=== Step 6: Configuring tunnel ingress (${#SUBDOMAINS[@]} subdomains)..."

# Build ingress JSON array
INGRESS_JSON="["
for sub in "${SUBDOMAINS[@]}"; do
    INGRESS_JSON+="{\"hostname\":\"${sub}.${DOMAIN}\",\"service\":\"${ORIGIN_SERVICE}\",\"originRequest\":{\"noTLSVerify\":true}},"
done
# Add catch-all (required)
INGRESS_JSON+="{\"service\":\"http_status:404\"}"
INGRESS_JSON+="]"

CONFIG_RESULT=$(cf_api PUT "/accounts/${ACCOUNT_ID}/cfd_tunnel/${TUNNEL_ID}/configurations" \
    "{\"config\":{\"ingress\":${INGRESS_JSON}}}")

if echo "$CONFIG_RESULT" | grep -q '"success":true'; then
    echo "    Ingress configured for ${#SUBDOMAINS[@]} subdomains."
else
    echo "WARNING: Tunnel config may have failed:"
    echo "$CONFIG_RESULT" | python3 -m json.tool 2>/dev/null || echo "$CONFIG_RESULT"
fi

# ── Step 7: Create DNS CNAME records ────────────────────────────────────────
echo "=== Step 7: Creating DNS records..."

CNAME_TARGET="${TUNNEL_ID}.cfargotunnel.com"
CREATED=0
EXISTED=0
FAILED=0

for sub in "${SUBDOMAINS[@]}"; do
    FQDN="${sub}.${DOMAIN}"

    # Check if record exists
    CHECK=$(cf_api GET "/zones/${ZONE_ID}/dns_records?name=${FQDN}&type=CNAME")
    HAS_RECORD=$(echo "$CHECK" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['result']))" 2>/dev/null)

    if [ "$HAS_RECORD" -gt 0 ] 2>/dev/null; then
        # Update existing record
        RECORD_ID=$(echo "$CHECK" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])" 2>/dev/null)
        UPDATE=$(cf_api PUT "/zones/${ZONE_ID}/dns_records/${RECORD_ID}" \
            "{\"type\":\"CNAME\",\"name\":\"${sub}\",\"content\":\"${CNAME_TARGET}\",\"proxied\":true}")
        if echo "$UPDATE" | grep -q '"success":true'; then
            ((EXISTED++))
        else
            echo "    WARN: Failed to update ${FQDN}"
            ((FAILED++))
        fi
    else
        # Create new record
        CREATE=$(cf_api POST "/zones/${ZONE_ID}/dns_records" \
            "{\"type\":\"CNAME\",\"name\":\"${sub}\",\"content\":\"${CNAME_TARGET}\",\"proxied\":true,\"ttl\":1}")
        if echo "$CREATE" | grep -q '"success":true'; then
            ((CREATED++))
        else
            echo "    WARN: Failed to create ${FQDN}"
            ((FAILED++))
        fi
    fi
done

echo "    DNS records: ${CREATED} created, ${EXISTED} updated, ${FAILED} failed"

# ── Step 8: Save tunnel token to .env ────────────────────────────────────────
echo "=== Step 8: Saving tunnel token to ${ENV_FILE}..."

if [ -f "$ENV_FILE" ]; then
    # Update existing .env
    if grep -q "CLOUDFLARE_TUNNEL_TOKEN" "$ENV_FILE"; then
        sed -i "s|^CLOUDFLARE_TUNNEL_TOKEN=.*|CLOUDFLARE_TUNNEL_TOKEN=${TUNNEL_TOKEN}|" "$ENV_FILE"
        echo "    Updated existing CLOUDFLARE_TUNNEL_TOKEN in .env"
    else
        echo "" >> "$ENV_FILE"
        echo "# Cloudflare Tunnel (auto-generated by cloudflare-tunnel-setup.sh)" >> "$ENV_FILE"
        echo "CLOUDFLARE_TUNNEL_TOKEN=${TUNNEL_TOKEN}" >> "$ENV_FILE"
        echo "    Appended CLOUDFLARE_TUNNEL_TOKEN to .env"
    fi
else
    cat > "$ENV_FILE" << ENVEOF
# Cloudflare Tunnel (auto-generated by cloudflare-tunnel-setup.sh)
CLOUDFLARE_TUNNEL_TOKEN=${TUNNEL_TOKEN}
ENVEOF
    echo "    Created .env with CLOUDFLARE_TUNNEL_TOKEN"
fi

# ── Step 9: Summary ─────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo "  CLOUDFLARE TUNNEL SETUP COMPLETE"
echo "================================================================"
echo ""
echo "  Tunnel:   ${TUNNEL_NAME} (${TUNNEL_ID})"
echo "  Domain:   ${DOMAIN}"
echo "  Services: ${#SUBDOMAINS[@]} subdomains configured"
echo "  Token:    saved to ${ENV_FILE}"
echo ""
echo "  Start the tunnel:"
echo "    cd ${INFRA_DIR}"
echo "    docker compose -p infra-stack up -d cloudflared"
echo ""
echo "  Your services will be available at:"
echo "  ──────────────────────────────────────────────────"
for sub in "${SUBDOMAINS[@]}"; do
    printf "    https://%-35s\n" "${sub}.${DOMAIN}"
done
echo "  ──────────────────────────────────────────────────"
echo ""
echo "  Tailscale URLs (also available):"
echo "    https://deepak-desktop.tailac51e7.ts.net/<path>/"
echo ""
echo "  Cloudflare Dashboard:"
echo "    https://dash.cloudflare.com → Zero Trust → Tunnels"
echo "================================================================"
