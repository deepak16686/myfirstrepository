#!/bin/bash
# =============================================================================
# PRODUCTION STACK — Bootstrap Setup Script
# =============================================================================
# Creates real, working credentials for all services after first boot.
# Run once after 'docker compose up -d' to configure tokens and API access.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
#
# What this script does:
#   1. Starts all services (or verifies they're running)
#   2. Waits for each service to become healthy
#   3. Creates admin users, API tokens, and org structures
#   4. Writes real tokens to .env
#   5. Restarts agents/runners with correct secrets
#   6. Prints a summary of all endpoints + credentials
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
CREDENTIALS_FILE="$SCRIPT_DIR/credentials.txt"

# Load current .env
set -a
source "$ENV_FILE"
set +a

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WAIT]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }
info()  { echo -e "${CYAN}[INFO]${NC} $1"; }

# -----------------------------------------------------------------------------
# Helper: wait for a service to respond
# -----------------------------------------------------------------------------
wait_for_service() {
    local name="$1"
    local url="$2"
    local max_attempts="${3:-60}"
    local attempt=0

    warn "Waiting for $name at $url ..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf -o /dev/null --max-time 5 "$url" 2>/dev/null; then
            log "$name is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 5
    done
    err "$name failed to start after $((max_attempts * 5))s"
    return 1
}

# Wait for a container to be healthy via docker inspect
wait_for_container() {
    local name="$1"
    local max_attempts="${2:-30}"
    local attempt=0

    warn "Waiting for container $name to be healthy..."
    while [ $attempt -lt $max_attempts ]; do
        local status=$(docker inspect --format='{{.State.Health.Status}}' "$name" 2>/dev/null || echo "missing")
        if [ "$status" = "healthy" ]; then
            log "$name is healthy"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 5
    done
    err "$name not healthy after $((max_attempts * 5))s"
    return 1
}

# Helper: update .env variable
update_env() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

# =============================================================================
echo ""
echo "=============================================="
echo "  PRODUCTION STACK — Bootstrap Setup"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Step 1: Start services
# -----------------------------------------------------------------------------
info "Starting all production services..."
cd "$SCRIPT_DIR"
docker compose up -d

# =============================================================================
# Step 2: Wait for core services
# =============================================================================
echo ""
info "--- Waiting for core services ---"
wait_for_container "prod-postgres" 30 || true
wait_for_container "prod-redis" 15 || true
wait_for_service "ChromaDB"    "http://localhost:${PROD_CHROMA_PORT:-18000}/api/v1/heartbeat" 30 || true
wait_for_service "Nexus"       "http://localhost:${PROD_NEXUS_UI_PORT:-18081}" 90
wait_for_service "SonarQube"   "http://localhost:${PROD_SONARQUBE_PORT:-19002}/api/system/status" 90

# =============================================================================
# Step 3: Setup Gitea — admin user + API token + orgs
# =============================================================================
echo ""
info "--- Setting up Gitea ---"
GITEA_PORT="${PROD_GITEA_HTTP_PORT:-13002}"
GITEA_URL="http://localhost:${GITEA_PORT}"

wait_for_service "Gitea" "${GITEA_URL}/api/healthz" 60

# Create admin user (ignore error if already exists)
info "Creating Gitea admin user..."
docker exec --user 1000 prod-gitea-server gitea admin user create \
    --username admin \
    --password admin123 \
    --email admin@prod.local \
    --admin \
    --must-change-password=false 2>/dev/null || log "Gitea admin user already exists"

# Create API token
info "Creating Gitea API token..."
GITEA_TOKEN_RESPONSE=$(curl -sf -X POST "${GITEA_URL}/api/v1/users/admin/tokens" \
    -u admin:admin123 \
    -H "Content-Type: application/json" \
    -d '{
        "name": "prod-api-token",
        "scopes": ["all"]
    }' 2>/dev/null || echo "")

if [ -n "$GITEA_TOKEN_RESPONSE" ]; then
    GITEA_TOKEN=$(echo "$GITEA_TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sha1',''))" 2>/dev/null || echo "")
    if [ -z "$GITEA_TOKEN" ]; then
        # Try python (Windows)
        GITEA_TOKEN=$(echo "$GITEA_TOKEN_RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin).get('sha1',''))" 2>/dev/null || echo "")
    fi
fi

if [ -n "$GITEA_TOKEN" ] && [ "$GITEA_TOKEN" != "" ]; then
    log "Gitea token created: ${GITEA_TOKEN}"
    update_env "PROD_GITEA_TOKEN" "$GITEA_TOKEN"
    update_env "PROD_JENKINS_GIT_TOKEN" "$GITEA_TOKEN"
else
    warn "Gitea token creation failed (may already exist). Use existing token or create manually."
fi

# Create orgs for Jenkins and GitHub Actions repos
info "Creating Gitea organizations..."
for ORG in jenkins-projects github-projects; do
    curl -sf -X POST "${GITEA_URL}/api/v1/orgs" \
        -u admin:admin123 \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"${ORG}\",\"visibility\":\"public\"}" 2>/dev/null || true
    log "Org '${ORG}' ready"
done

# Create runner registration token
info "Creating Gitea runner registration token..."
RUNNER_TOKEN_RESPONSE=$(curl -sf -X POST "${GITEA_URL}/api/v1/admin/runners/registration-token" \
    -u admin:admin123 \
    -H "Content-Type: application/json" 2>/dev/null || echo "")

if [ -n "$RUNNER_TOKEN_RESPONSE" ]; then
    RUNNER_TOKEN=$(echo "$RUNNER_TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || \
                   echo "$RUNNER_TOKEN_RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
fi

if [ -n "$RUNNER_TOKEN" ] && [ "$RUNNER_TOKEN" != "" ]; then
    log "Gitea runner token: ${RUNNER_TOKEN}"
    update_env "PROD_GITEA_RUNNER_TOKEN" "$RUNNER_TOKEN"
else
    warn "Could not get runner token. Register runner manually."
fi

# =============================================================================
# Step 4: Setup GitLab — PAT token
# =============================================================================
echo ""
info "--- Setting up GitLab ---"
GITLAB_PORT="${PROD_GITLAB_HTTP_PORT:-18929}"
GITLAB_URL="http://localhost:${GITLAB_PORT}"

wait_for_service "GitLab" "${GITLAB_URL}/users/sign_in" 180

info "Creating GitLab personal access token via rails..."
GITLAB_PAT=$(docker exec prod-gitlab-server gitlab-rails runner "
token = User.find_by(username: 'root').personal_access_tokens.create(
  scopes: ['api', 'read_repository', 'write_repository'],
  name: 'prod-api-token',
  expires_at: 365.days.from_now
)
token.set_token('glpat-prodstack-#{Time.now.to_i.to_s[-9..]}'  )
token.save!
puts token.token
" 2>/dev/null || echo "")

if [ -n "$GITLAB_PAT" ]; then
    # Extract just the token (last line of output)
    GITLAB_PAT=$(echo "$GITLAB_PAT" | tail -1 | tr -d '\r\n')
    log "GitLab PAT created: ${GITLAB_PAT}"
    update_env "PROD_GITLAB_TOKEN" "$GITLAB_PAT"
else
    warn "GitLab PAT creation failed. GitLab may still be initializing — re-run setup later."
fi

# Register GitLab runner
info "Registering GitLab runner..."
GITLAB_RUNNER_TOKEN=$(docker exec prod-gitlab-server gitlab-rails runner "
puts Gitlab::CurrentSettings.current_application_settings.runners_registration_token
" 2>/dev/null | tail -1 | tr -d '\r\n' || echo "")

if [ -n "$GITLAB_RUNNER_TOKEN" ]; then
    docker exec prod-gitlab-runner gitlab-runner register \
        --non-interactive \
        --url "http://prod-gitlab-server" \
        --registration-token "$GITLAB_RUNNER_TOKEN" \
        --executor docker \
        --docker-image "docker:24-dind" \
        --docker-privileged \
        --docker-network-mode "prod-platform-net" \
        --description "prod-runner" \
        --tag-list "docker,prod" 2>/dev/null && log "GitLab runner registered" || warn "GitLab runner registration failed"
else
    warn "Could not get GitLab runner registration token"
fi

# =============================================================================
# Step 5: Setup Jenkins — retrieve agent secrets
# =============================================================================
echo ""
info "--- Setting up Jenkins ---"
JENKINS_PORT="${PROD_JENKINS_PORT:-18080}"
JENKINS_URL="http://localhost:${JENKINS_PORT}/jenkins"

wait_for_service "Jenkins" "${JENKINS_URL}/login" 120

info "Retrieving Jenkins agent secrets..."
sleep 10  # Allow init scripts to finish

for i in 1 2 3; do
    AGENT_NAME="prod-agent-${i}"
    SECRET=$(curl -sf -u admin:admin123 \
        "${JENKINS_URL}/computer/${AGENT_NAME}/slave-agent.jnlp" 2>/dev/null | \
        grep -oP '<argument>\K[a-f0-9]{64}' | head -1 || echo "")

    if [ -n "$SECRET" ]; then
        log "Jenkins ${AGENT_NAME} secret: ${SECRET:0:16}..."
        update_env "PROD_JENKINS_AGENT_SECRET_${i}" "$SECRET"
    else
        warn "Could not retrieve secret for ${AGENT_NAME}. Jenkins nodes may need manual setup."
    fi
done

# =============================================================================
# Step 6: Setup SonarQube — change password + create token
# =============================================================================
echo ""
info "--- Setting up SonarQube ---"
SONAR_PORT="${PROD_SONARQUBE_PORT:-19002}"
SONAR_URL="http://localhost:${SONAR_PORT}"

wait_for_service "SonarQube" "${SONAR_URL}/api/system/status" 90

# Change default password (admin/admin → admin/<configured>)
info "Changing SonarQube admin password..."
curl -sf -X POST "${SONAR_URL}/api/users/change_password" \
    -u admin:admin \
    -d "login=admin&previousPassword=admin&password=${PROD_SONARQUBE_PASSWORD:-N7@qL9!fR2#XwA8\$}" 2>/dev/null \
    && log "SonarQube password changed" \
    || log "SonarQube password already changed"

# Create API token
info "Creating SonarQube API token..."
SONAR_TOKEN_RESPONSE=$(curl -sf -X POST "${SONAR_URL}/api/user_tokens/generate" \
    -u "admin:${PROD_SONARQUBE_PASSWORD:-N7@qL9!fR2#XwA8\$}" \
    -d "name=prod-api-token&type=GLOBAL_ANALYSIS_TOKEN" 2>/dev/null || echo "")

if [ -n "$SONAR_TOKEN_RESPONSE" ]; then
    SONAR_TOKEN=$(echo "$SONAR_TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || \
                  echo "$SONAR_TOKEN_RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null || echo "")
    if [ -n "$SONAR_TOKEN" ] && [ "$SONAR_TOKEN" != "" ]; then
        log "SonarQube token: ${SONAR_TOKEN}"
        update_env "PROD_SONARQUBE_TOKEN" "$SONAR_TOKEN"
    fi
else
    warn "SonarQube token creation failed (may already exist)"
fi

# =============================================================================
# Step 7: Setup Nexus — get admin password
# =============================================================================
echo ""
info "--- Setting up Nexus ---"
NEXUS_PORT="${PROD_NEXUS_UI_PORT:-18081}"

wait_for_service "Nexus" "http://localhost:${NEXUS_PORT}" 120

info "Retrieving Nexus initial admin password..."
NEXUS_INIT_PASS=$(docker exec prod-nexus cat /nexus-data/admin.password 2>/dev/null || echo "")
if [ -n "$NEXUS_INIT_PASS" ]; then
    log "Nexus initial password: ${NEXUS_INIT_PASS}"
    # Change password to configured value
    info "Changing Nexus admin password..."
    curl -sf -X PUT "http://localhost:${NEXUS_PORT}/service/rest/v1/security/users/admin/change-password" \
        -u "admin:${NEXUS_INIT_PASS}" \
        -H "Content-Type: text/plain" \
        -d "${PROD_NEXUS_PASSWORD:-r}" 2>/dev/null \
        && log "Nexus password changed to configured value" \
        || warn "Nexus password change failed"

    # Enable Docker Bearer Token Realm
    info "Enabling Nexus Docker realm..."
    curl -sf -X PUT "http://localhost:${NEXUS_PORT}/service/rest/v1/security/realms/active" \
        -u "admin:${PROD_NEXUS_PASSWORD:-r}" \
        -H "Content-Type: application/json" \
        -d '["NexusAuthenticatingRealm","DockerToken"]' 2>/dev/null \
        && log "Docker Bearer Token realm enabled" || true

    # Create Docker hosted repository on port 5001
    info "Creating Nexus Docker hosted repository..."
    curl -sf -X POST "http://localhost:${NEXUS_PORT}/service/rest/v1/repositories/docker/hosted" \
        -u "admin:${PROD_NEXUS_PASSWORD:-r}" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "docker-hosted",
            "online": true,
            "storage": {"blobStoreName": "default", "strictContentTypeValidation": true, "writePolicy": "ALLOW"},
            "docker": {"v1Enabled": false, "httpPort": 5001, "forceBasicAuth": false}
        }' 2>/dev/null \
        && log "Docker hosted repo created on port 5001" \
        || log "Docker repo may already exist"
else
    log "Nexus password already changed (initial password file removed)"
fi

# =============================================================================
# Step 8: Setup Splunk — create HEC token
# =============================================================================
echo ""
info "--- Setting up Splunk ---"
SPLUNK_UI_PORT="${PROD_SPLUNK_UI_PORT:-20000}"
SPLUNK_HEC_PORT="${PROD_SPLUNK_HEC_PORT:-18088}"

wait_for_service "Splunk" "http://localhost:${SPLUNK_UI_PORT}" 180

info "Creating Splunk HEC token via docker exec..."
docker exec prod-splunk curl -sfk -X POST "https://localhost:8089/servicesNS/admin/splunk_httpinput/data/inputs/http" \
    -u "admin:${PROD_SPLUNK_PASSWORD:-Admin@1234}" \
    -d "name=prod-hec-token&index=main&sourcetype=_json" 2>/dev/null || true

# Get the token value (parse XML since Splunk REST API returns XML by default)
SPLUNK_HEC_TOKEN=$(docker exec prod-splunk curl -sfk \
    "https://localhost:8089/servicesNS/admin/splunk_httpinput/data/inputs/http/http%3A%252F%252Fprod-hec-token?output_mode=json" \
    -u "admin:${PROD_SPLUNK_PASSWORD:-Admin@1234}" 2>/dev/null | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['entry'][0]['content']['token'])" 2>/dev/null || echo "")

if [ -n "$SPLUNK_HEC_TOKEN" ] && [ "$SPLUNK_HEC_TOKEN" != "" ]; then
    log "Splunk HEC token: ${SPLUNK_HEC_TOKEN}"
    update_env "PROD_SPLUNK_TOKEN" "$SPLUNK_HEC_TOKEN"
else
    warn "Splunk HEC token creation failed. Create manually via UI at https://localhost:${SPLUNK_UI_PORT}"
fi

# =============================================================================
# Step 9: Restart agents/runners with updated secrets
# =============================================================================
echo ""
info "--- Restarting agents with updated credentials ---"

# Reload .env
set -a
source "$ENV_FILE"
set +a

# Restart Jenkins agents (they need the real secrets)
info "Restarting Jenkins agents with real secrets..."
docker compose -f "$SCRIPT_DIR/scm.yml" up -d \
    prod-jenkins-agent-1 prod-jenkins-agent-2 prod-jenkins-agent-3 2>/dev/null || true

# Restart Gitea runner with real token
info "Restarting Gitea runner with real token..."
docker compose -f "$SCRIPT_DIR/scm.yml" up -d prod-gitea-runner 2>/dev/null || true

# Restart backend with real tokens
info "Restarting backend with updated tokens..."
docker compose -f "$SCRIPT_DIR/apps.yml" up -d 2>/dev/null || true

log "Agent restart complete"

# =============================================================================
# Step 10: Generate credentials summary
# =============================================================================
echo ""
info "--- Generating credentials summary ---"

# Reload final .env
set -a
source "$ENV_FILE"
set +a

cat > "$CREDENTIALS_FILE" << CREDS
# =============================================================================
# PRODUCTION STACK — Credentials & Endpoints
# Generated: $(date)
# =============================================================================

## CORE INFRASTRUCTURE
PostgreSQL:     localhost:${PROD_POSTGRES_PORT:-15432}   user=${PROD_POSTGRES_USER:-postgres}  pass=${PROD_POSTGRES_PASSWORD:-postgres}  db=${PROD_POSTGRES_DB:-modernization}
Redis:          localhost:${PROD_REDIS_PORT:-16379}      (no auth)
MinIO:          http://localhost:${PROD_MINIO_PORT:-19000}        user=${PROD_MINIO_ROOT_USER:-minioadmin}  pass=${PROD_MINIO_ROOT_PASSWORD:-minioadmin123}
MinIO Console:  http://localhost:${PROD_MINIO_CONSOLE_PORT:-19001}

## AI / ML
Ollama:         http://localhost:${PROD_OLLAMA_PORT:-21434}
ChromaDB:       http://localhost:${PROD_CHROMA_PORT:-18000}
Open WebUI:     http://localhost:${PROD_OPENWEBUI_PORT:-13001}

## SOURCE CONTROL & CI/CD
GitLab:         http://localhost:${PROD_GITLAB_HTTP_PORT:-18929}   user=root  pass=${PROD_GITLAB_ROOT_PASSWORD:-ChangeMe123!}
GitLab Token:   ${PROD_GITLAB_TOKEN}
Gitea:          http://localhost:${PROD_GITEA_HTTP_PORT:-13002}    user=admin  pass=admin123
Gitea Token:    ${PROD_GITEA_TOKEN}
Jenkins:        http://localhost:${PROD_JENKINS_PORT:-18080}/jenkins   user=admin  pass=admin123

## CODE QUALITY & SECURITY
SonarQube:      http://localhost:${PROD_SONARQUBE_PORT:-19002}     user=admin  pass=${PROD_SONARQUBE_PASSWORD}
SonarQube Token: ${PROD_SONARQUBE_TOKEN:-<run setup again after SonarQube is ready>}
Nexus:          http://localhost:${PROD_NEXUS_UI_PORT:-18081}      user=admin  pass=${PROD_NEXUS_PASSWORD:-r}
Nexus Registry: localhost:${PROD_NEXUS_REGISTRY_PORT:-15001}
Trivy:          http://localhost:${PROD_TRIVY_PORT:-18083}

## MONITORING
Prometheus:     http://localhost:${PROD_PROMETHEUS_PORT:-19090}
Grafana:        http://localhost:${PROD_GRAFANA_PORT:-13000}       user=admin  pass=${PROD_GRAFANA_ADMIN_PASSWORD:-admin123}
Loki:           http://localhost:${PROD_LOKI_PORT:-13100}
Jaeger:         http://localhost:${PROD_JAEGER_UI_PORT:-26686}
Splunk:         https://localhost:${PROD_SPLUNK_UI_PORT:-20000}    user=admin  pass=${PROD_SPLUNK_PASSWORD:-Admin@1234}
Splunk HEC:     https://localhost:${PROD_SPLUNK_HEC_PORT:-18088}   token=${PROD_SPLUNK_TOKEN}

## PROJECT MANAGEMENT
Redmine:        http://localhost:${PROD_REDMINE_PORT:-18090}       user=admin  pass=admin

## APPLICATIONS
Backend:        http://localhost:${PROD_BACKEND_PORT:-18003}
Modernization:  http://localhost:${PROD_MODERNIZATION_API_PORT:-18002}
CREDS

log "Credentials written to: $CREDENTIALS_FILE"

# =============================================================================
# Final summary
# =============================================================================
echo ""
echo "=============================================="
echo -e "  ${GREEN}PRODUCTION STACK SETUP COMPLETE${NC}"
echo "=============================================="
echo ""
echo "  Endpoints & credentials saved to:"
echo "    $CREDENTIALS_FILE"
echo ""
echo "  Quick verification:"
echo "    docker ps --filter name=prod- --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
echo ""
echo "  To tear down:"
echo "    cd $SCRIPT_DIR && docker compose down"
echo ""
echo "  To bring up a single group:"
echo "    docker compose -f core.yml up -d"
echo ""
echo "=============================================="
