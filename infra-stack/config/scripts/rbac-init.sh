#!/bin/sh
# rbac-init.sh — creates RBAC groups + service accounts across all DevOps tools.
# Idempotent — safe to re-run if a tool was temporarily unavailable.
set -e

echo "============================================================"
echo "  RBAC Initialization - Groups & Service Accounts"
echo "============================================================"

if [ -z "$VAULT_TOKEN" ] && [ -f /vault/file/.root-token ]; then
    export VAULT_TOKEN=$(cat /vault/file/.root-token)
fi

apk add --no-cache curl jq >/dev/null 2>&1

SVC_USER="svc-devops-backend"
SVC_EMAIL="svc-backend@devops.local"
SVC_PASS="SvcD3v0ps2026"

check_tool() {
    local name="$1" url="$2"
    echo -n "Waiting for ${name}..."
    for i in $(seq 1 30); do
        if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -qE "^(200|302|401|403)$"; then
            echo " ready"; return 0
        fi
        echo -n "."; sleep 3
    done
    echo " TIMEOUT (skipping ${name})"; return 1
}

setup_gitlab() {
    echo ""; echo "=== GitLab RBAC ==="
    GITLAB_URL="http://gitlab-server:80"
    GITLAB_TOKEN=$(vault kv get -field=token secret/gitlab 2>/dev/null || echo "")
    [ -z "$GITLAB_TOKEN" ] && echo "SKIP: No GitLab admin token in Vault" && return
    GL_HEADER="PRIVATE-TOKEN: ${GITLAB_TOKEN}"

    for group in devops-readonly devops-readwrite devops-admin; do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${GITLAB_URL}/api/v4/groups" \
            -H "$GL_HEADER" -H "Content-Type: application/json" \
            -d "{\"name\":\"${group}\",\"path\":\"${group}\",\"visibility\":\"private\"}")
        [ "$STATUS" = "201" ] && echo "  Group created: ${group}" || echo "  Group exists/error: ${group} (${STATUS})"
    done

    EXISTING=$(curl -s -H "$GL_HEADER" "${GITLAB_URL}/api/v4/users?username=${SVC_USER}" | jq 'length')
    if [ "$EXISTING" = "0" ]; then
        SVC_RESPONSE=$(curl -s -X POST "${GITLAB_URL}/api/v4/users" -H "$GL_HEADER" -H "Content-Type: application/json" \
            -d "{\"username\":\"${SVC_USER}\",\"name\":\"Backend Service Account\",\"email\":\"${SVC_EMAIL}\",\"password\":\"${SVC_PASS}\",\"skip_confirmation\":true,\"admin\":false}")
        SVC_ID=$(echo "$SVC_RESPONSE" | jq -r '.id // empty')
    else
        SVC_ID=$(curl -s -H "$GL_HEADER" "${GITLAB_URL}/api/v4/users?username=${SVC_USER}" | jq -r '.[0].id')
    fi
    echo "  Service account: ${SVC_USER} (id: ${SVC_ID})"

    TOKEN_RESPONSE=$(curl -s -X POST "${GITLAB_URL}/api/v4/users/${SVC_ID}/impersonation_tokens" \
        -H "$GL_HEADER" -H "Content-Type: application/json" \
        -d "{\"name\":\"vault-managed\",\"scopes\":[\"api\",\"read_repository\",\"write_repository\"],\"expires_at\":\"2027-02-16\"}")
    SVC_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.token // empty')
    [ -n "$SVC_TOKEN" ] && vault kv put secret/service-accounts/gitlab token="$SVC_TOKEN" username="$SVC_USER"
}

setup_gitea() {
    echo ""; echo "=== Gitea RBAC ==="
    GITEA_URL="http://gitea-server:3000"
    GITEA_TOKEN=$(vault kv get -field=token secret/gitea 2>/dev/null || echo "")
    [ -z "$GITEA_TOKEN" ] && echo "SKIP: No Gitea admin token in Vault" && return
    GT_AUTH="Authorization: token ${GITEA_TOKEN}"

    EXISTING=$(curl -s -H "$GT_AUTH" "${GITEA_URL}/api/v1/users/${SVC_USER}" -o /dev/null -w "%{http_code}")
    [ "$EXISTING" = "404" ] && curl -s -X POST "${GITEA_URL}/api/v1/admin/users" -H "$GT_AUTH" -H "Content-Type: application/json" \
        -d "{\"username\":\"${SVC_USER}\",\"password\":\"${SVC_PASS}\",\"email\":\"${SVC_EMAIL}\",\"must_change_password\":false}" >/dev/null \
        && echo "  Service account created: ${SVC_USER}" || echo "  Service account exists: ${SVC_USER}"

    for ORG in jenkins-projects github-projects; do
        for TEAM_PERM in "devops-readonly:read" "devops-readwrite:write" "devops-admin:admin"; do
            TEAM_NAME="${TEAM_PERM%%:*}"; PERM="${TEAM_PERM##*:}"
            TEAM_ID=$(curl -s -H "$GT_AUTH" "${GITEA_URL}/api/v1/orgs/${ORG}/teams" | jq -r ".[] | select(.name==\"${TEAM_NAME}\") | .id // empty")
            if [ -z "$TEAM_ID" ]; then
                TEAM_RESPONSE=$(curl -s -X POST "${GITEA_URL}/api/v1/orgs/${ORG}/teams" -H "$GT_AUTH" -H "Content-Type: application/json" \
                    -d "{\"name\":\"${TEAM_NAME}\",\"permission\":\"${PERM}\",\"includes_all_repositories\":true,\"units\":[\"repo.code\",\"repo.issues\",\"repo.pulls\"]}")
                TEAM_ID=$(echo "$TEAM_RESPONSE" | jq -r '.id // empty')
            fi
            [ "$TEAM_NAME" = "devops-admin" ] && [ -n "$TEAM_ID" ] && \
                curl -s -o /dev/null -X PUT "${GITEA_URL}/api/v1/teams/${TEAM_ID}/members/${SVC_USER}" -H "$GT_AUTH"
        done
    done

    EXISTING_TOKEN=$(vault kv get -field=token secret/service-accounts/gitea 2>/dev/null || echo "")
    if [ -z "$EXISTING_TOKEN" ]; then
        TOKEN_RESPONSE=$(curl -s -X POST "${GITEA_URL}/api/v1/users/${SVC_USER}/tokens" \
            -u "${SVC_USER}:${SVC_PASS}" -H "Content-Type: application/json" \
            -d "{\"name\":\"vault-managed\",\"scopes\":[\"write:repository\",\"write:user\",\"write:organization\"]}")
        SVC_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.sha1 // empty')
        [ -n "$SVC_TOKEN" ] && vault kv put secret/service-accounts/gitea token="$SVC_TOKEN" username="$SVC_USER"
    fi
}

setup_sonarqube() {
    echo ""; echo "=== SonarQube RBAC ==="
    SONAR_URL="http://ai-sonarqube:9000"
    SONAR_PASS=$(vault kv get -field=password secret/sonarqube 2>/dev/null || echo "admin")
    for GROUP in devops-readonly devops-readwrite devops-admin; do
        curl -s -o /dev/null -X POST "${SONAR_URL}/api/user_groups/create" -u "admin:${SONAR_PASS}" -d "name=${GROUP}" 2>/dev/null || true
    done
    EXISTING=$(curl -s -u "admin:${SONAR_PASS}" "${SONAR_URL}/api/users/search?q=${SVC_USER}" | jq '.users | length')
    [ "$EXISTING" = "0" ] && curl -s -o /dev/null -X POST "${SONAR_URL}/api/users/create" -u "admin:${SONAR_PASS}" \
        -d "login=${SVC_USER}&name=Backend+Service+Account&password=${SVC_PASS}&local=true"
    curl -s -o /dev/null -X POST "${SONAR_URL}/api/user_groups/add_user" -u "admin:${SONAR_PASS}" -d "name=devops-readwrite&login=${SVC_USER}"
    EXISTING_TOKEN=$(vault kv get -field=token secret/service-accounts/sonarqube 2>/dev/null || echo "")
    if [ -z "$EXISTING_TOKEN" ]; then
        TOKEN_RESPONSE=$(curl -s -X POST "${SONAR_URL}/api/user_tokens/generate" -u "admin:${SONAR_PASS}" -d "login=${SVC_USER}&name=vault-managed")
        SVC_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.token // empty')
        [ -n "$SVC_TOKEN" ] && vault kv put secret/service-accounts/sonarqube token="$SVC_TOKEN" username="$SVC_USER" password="$SVC_PASS"
    fi
    echo "  SonarQube RBAC done"
}

setup_nexus() {
    echo ""; echo "=== Nexus RBAC ==="
    NEXUS_URL="http://ai-nexus:8081"
    NEXUS_PASS=$(vault kv get -field=password secret/nexus 2>/dev/null || echo "r")
    for i in $(seq 1 20); do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "admin:${NEXUS_PASS}" "${NEXUS_URL}/service/rest/v1/status")
        [ "$STATUS" = "200" ] && break; sleep 5
    done
    USER_EXISTS=$(curl -s -u "admin:${NEXUS_PASS}" "${NEXUS_URL}/service/rest/v1/security/users" | jq -r ".[].userId" | grep -c "^${SVC_USER}$" 2>/dev/null || echo "0")
    if [ "$USER_EXISTS" = "0" ]; then
        curl -s -o /dev/null -X POST "${NEXUS_URL}/service/rest/v1/security/users" -u "admin:${NEXUS_PASS}" \
            -H "Content-Type: application/json" \
            -d "{\"userId\":\"${SVC_USER}\",\"firstName\":\"Backend\",\"lastName\":\"Service\",\"emailAddress\":\"${SVC_EMAIL}\",\"password\":\"${SVC_PASS}\",\"status\":\"active\",\"roles\":[\"devops-readwrite\"]}"
    fi
    vault kv put secret/service-accounts/nexus username="$SVC_USER" password="$SVC_PASS"
    echo "  Nexus RBAC done"
}

setup_jenkins() {
    echo ""; echo "=== Jenkins RBAC ==="
    vault kv put secret/service-accounts/jenkins username="$SVC_USER" password="$SVC_PASS"
    echo "  Jenkins RBAC via Groovy init script. Credentials stored in Vault."
}

if check_tool "GitLab" "http://gitlab-server:80/users/sign_in"; then setup_gitlab; fi
if check_tool "Gitea" "http://gitea-server:3000/api/v1/version"; then setup_gitea; fi
if check_tool "SonarQube" "http://ai-sonarqube:9000/api/system/status"; then setup_sonarqube; fi
if check_tool "Nexus" "http://ai-nexus:8081/service/rest/v1/status"; then setup_nexus; fi
if check_tool "Jenkins" "http://jenkins-master:8080/jenkins/login"; then setup_jenkins; fi

echo ""
echo "============================================================"
echo "  RBAC Initialization Complete"
echo "  Groups: devops-readonly, devops-readwrite, devops-admin"
echo "  Service account: ${SVC_USER}"
echo "  Credentials: secret/service-accounts/{tool}"
echo "============================================================"
