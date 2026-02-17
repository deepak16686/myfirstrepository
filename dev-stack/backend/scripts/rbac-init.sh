#!/bin/sh
set -e

echo "============================================================"
echo "  RBAC Initialization - Groups & Service Accounts"
echo "============================================================"
echo ""

# Install curl and jq (vault image only has wget)
apk add --no-cache curl jq >/dev/null 2>&1

SVC_USER="svc-devops-backend"
SVC_EMAIL="svc-backend@devops.local"
SVC_PASS="SvcD3v0ps2026"

# ============================================================
# Helper functions
# ============================================================

check_tool() {
    local name="$1"
    local url="$2"
    echo -n "Waiting for ${name}..."
    for i in $(seq 1 30); do
        if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -qE "^(200|302|401|403)$"; then
            echo " ready"
            return 0
        fi
        echo -n "."
        sleep 3
    done
    echo " TIMEOUT (skipping ${name})"
    return 1
}

# ============================================================
# 1. GitLab - Groups & Service Account
# ============================================================

setup_gitlab() {
    echo ""
    echo "=== GitLab RBAC ==="

    GITLAB_URL="http://gitlab-server:80"
    GITLAB_TOKEN=$(vault kv get -field=token secret/gitlab 2>/dev/null || echo "")

    if [ -z "$GITLAB_TOKEN" ]; then
        echo "SKIP: No GitLab admin token in Vault (set via: docker exec -e VAULT_TOKEN=dev-root-token vault vault kv put secret/gitlab token=glpat-xxx)"
        return
    fi

    GL_HEADER="PRIVATE-TOKEN: ${GITLAB_TOKEN}"

    # Create groups (idempotent - 409 if exists)
    for group in devops-readonly devops-readwrite devops-admin; do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${GITLAB_URL}/api/v4/groups" \
            -H "$GL_HEADER" -H "Content-Type: application/json" \
            -d "{\"name\":\"${group}\",\"path\":\"${group}\",\"visibility\":\"private\"}")
        if [ "$STATUS" = "201" ]; then
            echo "  Group created: ${group}"
        elif [ "$STATUS" = "400" ]; then
            echo "  Group exists: ${group}"
        else
            echo "  Group ${group}: HTTP ${STATUS}"
        fi
    done

    # Check if service account exists
    EXISTING=$(curl -s -H "$GL_HEADER" "${GITLAB_URL}/api/v4/users?username=${SVC_USER}" | jq 'length')
    if [ "$EXISTING" = "0" ]; then
        # Create service account user
        SVC_RESPONSE=$(curl -s -X POST "${GITLAB_URL}/api/v4/users" \
            -H "$GL_HEADER" -H "Content-Type: application/json" \
            -d "{\"username\":\"${SVC_USER}\",\"name\":\"Backend Service Account\",\"email\":\"${SVC_EMAIL}\",\"password\":\"${SVC_PASS}\",\"skip_confirmation\":true,\"admin\":false}")
        SVC_ID=$(echo "$SVC_RESPONSE" | jq -r '.id // empty')
        if [ -n "$SVC_ID" ]; then
            echo "  Service account created: ${SVC_USER} (id: ${SVC_ID})"
        else
            echo "  WARN: Failed to create service account: $(echo "$SVC_RESPONSE" | jq -r '.message // .error // "unknown error"')"
            return
        fi
    else
        SVC_ID=$(curl -s -H "$GL_HEADER" "${GITLAB_URL}/api/v4/users?username=${SVC_USER}" | jq -r '.[0].id')
        echo "  Service account exists: ${SVC_USER} (id: ${SVC_ID})"
    fi

    # Create impersonation token for service account
    TOKEN_RESPONSE=$(curl -s -X POST "${GITLAB_URL}/api/v4/users/${SVC_ID}/impersonation_tokens" \
        -H "$GL_HEADER" -H "Content-Type: application/json" \
        -d "{\"name\":\"vault-managed\",\"scopes\":[\"api\",\"read_repository\",\"write_repository\"],\"expires_at\":\"2027-02-16\"}")
    SVC_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.token // empty')
    if [ -n "$SVC_TOKEN" ]; then
        vault kv put secret/service-accounts/gitlab token="$SVC_TOKEN" username="$SVC_USER"
        echo "  Service account token stored in Vault"
    else
        # Token might already exist - check existing
        EXISTING_TOKEN=$(vault kv get -field=token secret/service-accounts/gitlab 2>/dev/null || echo "")
        if [ -n "$EXISTING_TOKEN" ]; then
            echo "  Service account token already in Vault"
        else
            echo "  WARN: Could not create token: $(echo "$TOKEN_RESPONSE" | jq -r '.message // .error // "already exists"')"
        fi
    fi

    # Add service account to devops-admin group
    ADMIN_GRP_ID=$(curl -s -H "$GL_HEADER" "${GITLAB_URL}/api/v4/groups?search=devops-admin" | jq -r '.[0].id // empty')
    if [ -n "$ADMIN_GRP_ID" ]; then
        curl -s -o /dev/null -X POST "${GITLAB_URL}/api/v4/groups/${ADMIN_GRP_ID}/members" \
            -H "$GL_HEADER" -H "Content-Type: application/json" \
            -d "{\"user_id\":${SVC_ID},\"access_level\":40}" 2>/dev/null
        echo "  Service account added to devops-admin group"
    fi
}

# ============================================================
# 2. Gitea - Teams & Service Account
# ============================================================

setup_gitea() {
    echo ""
    echo "=== Gitea RBAC ==="

    GITEA_URL="http://gitea-server:3000"
    GITEA_TOKEN=$(vault kv get -field=token secret/gitea 2>/dev/null || echo "")

    if [ -z "$GITEA_TOKEN" ]; then
        echo "SKIP: No Gitea admin token in Vault"
        return
    fi

    GT_AUTH="Authorization: token ${GITEA_TOKEN}"

    # Create service account user (idempotent)
    EXISTING=$(curl -s -H "$GT_AUTH" "${GITEA_URL}/api/v1/users/${SVC_USER}" -o /dev/null -w "%{http_code}")
    if [ "$EXISTING" = "404" ]; then
        curl -s -X POST "${GITEA_URL}/api/v1/admin/users" \
            -H "$GT_AUTH" -H "Content-Type: application/json" \
            -d "{\"username\":\"${SVC_USER}\",\"password\":\"${SVC_PASS}\",\"email\":\"${SVC_EMAIL}\",\"must_change_password\":false,\"visibility\":\"private\"}" >/dev/null
        echo "  Service account created: ${SVC_USER}"
    else
        echo "  Service account exists: ${SVC_USER}"
    fi

    # Create teams in each org
    for ORG in jenkins-projects github-projects; do
        echo "  Org: ${ORG}"
        for TEAM_PERM in "devops-readonly:read" "devops-readwrite:write" "devops-admin:admin"; do
            TEAM_NAME="${TEAM_PERM%%:*}"
            PERM="${TEAM_PERM##*:}"

            # Check if team exists
            TEAM_ID=$(curl -s -H "$GT_AUTH" "${GITEA_URL}/api/v1/orgs/${ORG}/teams" | \
                jq -r ".[] | select(.name==\"${TEAM_NAME}\") | .id // empty")

            if [ -z "$TEAM_ID" ]; then
                TEAM_RESPONSE=$(curl -s -X POST "${GITEA_URL}/api/v1/orgs/${ORG}/teams" \
                    -H "$GT_AUTH" -H "Content-Type: application/json" \
                    -d "{\"name\":\"${TEAM_NAME}\",\"permission\":\"${PERM}\",\"includes_all_repositories\":true,\"units\":[\"repo.code\",\"repo.issues\",\"repo.pulls\",\"repo.releases\",\"repo.actions\"]}")
                TEAM_ID=$(echo "$TEAM_RESPONSE" | jq -r '.id // empty')
                echo "    Team created: ${TEAM_NAME} (${PERM}) -> id: ${TEAM_ID}"
            else
                echo "    Team exists: ${TEAM_NAME} (id: ${TEAM_ID})"
            fi

            # Add service account to admin team
            if [ "$TEAM_NAME" = "devops-admin" ] && [ -n "$TEAM_ID" ]; then
                curl -s -o /dev/null -X PUT "${GITEA_URL}/api/v1/teams/${TEAM_ID}/members/${SVC_USER}" \
                    -H "$GT_AUTH"
                echo "    Service account added to ${TEAM_NAME}"
            fi
        done
    done

    # Create token for service account (must use service account's own credentials)
    EXISTING_TOKEN=$(vault kv get -field=token secret/service-accounts/gitea 2>/dev/null || echo "")
    if [ -z "$EXISTING_TOKEN" ]; then
        TOKEN_RESPONSE=$(curl -s -X POST "${GITEA_URL}/api/v1/users/${SVC_USER}/tokens" \
            -u "${SVC_USER}:${SVC_PASS}" -H "Content-Type: application/json" \
            -d "{\"name\":\"vault-managed\",\"scopes\":[\"write:repository\",\"write:user\",\"write:organization\",\"write:issue\"]}")
        SVC_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.sha1 // empty')
        if [ -n "$SVC_TOKEN" ]; then
            vault kv put secret/service-accounts/gitea token="$SVC_TOKEN" username="$SVC_USER"
            echo "  Service account token stored in Vault"
        else
            echo "  WARN: Could not create token: $(echo "$TOKEN_RESPONSE" | jq -r '.message // "unknown"')"
        fi
    else
        echo "  Service account token already in Vault"
    fi
}

# ============================================================
# 3. SonarQube - Groups & Service Account
# ============================================================

setup_sonarqube() {
    echo ""
    echo "=== SonarQube RBAC ==="

    SONAR_URL="http://ai-sonarqube:9000"
    SONAR_PASS=$(vault kv get -field=password secret/sonarqube 2>/dev/null || echo "admin")
    SONAR_AUTH="admin:${SONAR_PASS}"

    # Create groups
    for GROUP in devops-readonly devops-readwrite devops-admin; do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${SONAR_URL}/api/user_groups/create" \
            -u "$SONAR_AUTH" -d "name=${GROUP}&description=${GROUP} access group")
        if [ "$STATUS" = "200" ]; then
            echo "  Group created: ${GROUP}"
        else
            echo "  Group exists or error: ${GROUP} (HTTP ${STATUS})"
        fi
    done

    # Set permissions for each group
    # devops-readonly: browse projects
    for PERM in user scan; do
        curl -s -o /dev/null -X POST "${SONAR_URL}/api/permissions/add_group" \
            -u "$SONAR_AUTH" -d "groupName=devops-readonly&permission=${PERM}"
    done
    echo "  Permissions set: devops-readonly (user, scan)"

    # devops-readwrite: browse + create projects + scan
    for PERM in user scan provisioning; do
        curl -s -o /dev/null -X POST "${SONAR_URL}/api/permissions/add_group" \
            -u "$SONAR_AUTH" -d "groupName=devops-readwrite&permission=${PERM}"
    done
    echo "  Permissions set: devops-readwrite (user, scan, provisioning)"

    # devops-admin: full admin
    for PERM in admin user scan provisioning; do
        curl -s -o /dev/null -X POST "${SONAR_URL}/api/permissions/add_group" \
            -u "$SONAR_AUTH" -d "groupName=devops-admin&permission=${PERM}"
    done
    echo "  Permissions set: devops-admin (admin, user, scan, provisioning)"

    # Create service account
    EXISTING=$(curl -s -u "$SONAR_AUTH" "${SONAR_URL}/api/users/search?q=${SVC_USER}" | jq '.users | length')
    if [ "$EXISTING" = "0" ]; then
        curl -s -o /dev/null -X POST "${SONAR_URL}/api/users/create" \
            -u "$SONAR_AUTH" \
            -d "login=${SVC_USER}&name=Backend+Service+Account&password=${SVC_PASS}&local=true"
        echo "  Service account created: ${SVC_USER}"
    else
        echo "  Service account exists: ${SVC_USER}"
    fi

    # Add to devops-readwrite group
    curl -s -o /dev/null -X POST "${SONAR_URL}/api/user_groups/add_user" \
        -u "$SONAR_AUTH" -d "name=devops-readwrite&login=${SVC_USER}"
    echo "  Service account added to devops-readwrite"

    # Generate token
    EXISTING_TOKEN=$(vault kv get -field=token secret/service-accounts/sonarqube 2>/dev/null || echo "")
    if [ -z "$EXISTING_TOKEN" ]; then
        TOKEN_RESPONSE=$(curl -s -X POST "${SONAR_URL}/api/user_tokens/generate" \
            -u "$SONAR_AUTH" -d "login=${SVC_USER}&name=vault-managed")
        SVC_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.token // empty')
        if [ -n "$SVC_TOKEN" ]; then
            vault kv put secret/service-accounts/sonarqube \
                token="$SVC_TOKEN" username="$SVC_USER" password="$SVC_PASS"
            echo "  Service account token stored in Vault"
        else
            echo "  WARN: Could not create token (may already exist)"
        fi
    else
        echo "  Service account token already in Vault"
    fi
}

# ============================================================
# 4. Nexus - Roles & Service Account
# ============================================================

setup_nexus() {
    echo ""
    echo "=== Nexus RBAC ==="

    NEXUS_URL="http://ai-nexus:8081"
    NEXUS_USER=$(vault kv get -field=username secret/nexus 2>/dev/null || echo "admin")
    NEXUS_PASS=$(vault kv get -field=password secret/nexus 2>/dev/null || echo "admin123")
    NEXUS_AUTH="${NEXUS_USER}:${NEXUS_PASS}"

    # Wait for Nexus to be fully ready (takes longer than healthcheck)
    for i in $(seq 1 20); do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -u "$NEXUS_AUTH" "${NEXUS_URL}/service/rest/v1/status")
        if [ "$STATUS" = "200" ]; then
            break
        fi
        echo "  Nexus not ready (${STATUS}), waiting..."
        sleep 5
    done

    # Create roles (idempotent - POST returns 400 if exists, so try create, ignore if exists)
    # devops-readonly
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${NEXUS_URL}/service/rest/v1/security/roles" \
        -u "$NEXUS_AUTH" -H "Content-Type: application/json" \
        -d '{"id":"devops-readonly","name":"devops-readonly","description":"Read-only access","privileges":["nx-repository-view-*-*-browse","nx-repository-view-*-*-read","nx-search-read","nx-healthcheck-read"],"roles":[]}')
    [ "$STATUS" = "200" ] && echo "  Role created: devops-readonly" || echo "  Role exists: devops-readonly (${STATUS})"

    # devops-readwrite
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${NEXUS_URL}/service/rest/v1/security/roles" \
        -u "$NEXUS_AUTH" -H "Content-Type: application/json" \
        -d '{"id":"devops-readwrite","name":"devops-readwrite","description":"Read-write access","privileges":["nx-repository-view-*-*-browse","nx-repository-view-*-*-read","nx-repository-view-*-*-add","nx-repository-view-*-*-edit","nx-component-upload","nx-search-read","nx-healthcheck-read"],"roles":[]}')
    [ "$STATUS" = "200" ] && echo "  Role created: devops-readwrite" || echo "  Role exists: devops-readwrite (${STATUS})"

    # devops-admin
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${NEXUS_URL}/service/rest/v1/security/roles" \
        -u "$NEXUS_AUTH" -H "Content-Type: application/json" \
        -d '{"id":"devops-admin","name":"devops-admin","description":"Full admin access","privileges":["nx-all"],"roles":[]}')
    [ "$STATUS" = "200" ] && echo "  Role created: devops-admin" || echo "  Role exists: devops-admin (${STATUS})"

    # Create service account user (check via user list since single-user GET is unsupported)
    USER_EXISTS=$(curl -s -u "$NEXUS_AUTH" "${NEXUS_URL}/service/rest/v1/security/users" | jq -r ".[].userId" | grep -c "^${SVC_USER}$" 2>/dev/null || echo "0")
    if [ "$USER_EXISTS" = "0" ]; then
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${NEXUS_URL}/service/rest/v1/security/users" \
            -u "$NEXUS_AUTH" -H "Content-Type: application/json" \
            -d "{\"userId\":\"${SVC_USER}\",\"firstName\":\"Backend\",\"lastName\":\"Service\",\"emailAddress\":\"${SVC_EMAIL}\",\"password\":\"${SVC_PASS}\",\"status\":\"active\",\"roles\":[\"devops-readwrite\"]}")
        echo "  Service account created: ${SVC_USER} (role: devops-readwrite, HTTP: ${STATUS})"
    else
        echo "  Service account exists: ${SVC_USER}"
    fi

    # Store in Vault
    vault kv put secret/service-accounts/nexus \
        username="$SVC_USER" password="$SVC_PASS"
    echo "  Service account credentials stored in Vault"
}

# ============================================================
# 5. Jenkins - handled by Groovy init script (03-rbac-init.groovy)
#    Just store the credentials in Vault
# ============================================================

setup_jenkins() {
    echo ""
    echo "=== Jenkins RBAC ==="
    echo "  Jenkins RBAC is configured via Groovy init script (03-rbac-init.groovy)"
    echo "  Storing service account credentials in Vault..."

    JENKINS_URL="http://jenkins-master:8080/jenkins"

    # The Groovy script creates the user, but we need to get an API token
    # For now, store username/password - the Groovy script handles RBAC
    vault kv put secret/service-accounts/jenkins \
        username="$SVC_USER" password="$SVC_PASS"
    echo "  Service account credentials stored in Vault"
}

# ============================================================
# Run all setups
# ============================================================

echo "Checking tool availability..."

if check_tool "GitLab" "http://gitlab-server:80/users/sign_in"; then
    setup_gitlab
fi

if check_tool "Gitea" "http://gitea-server:3000/api/v1/version"; then
    setup_gitea
fi

if check_tool "SonarQube" "http://ai-sonarqube:9000/api/system/status"; then
    setup_sonarqube
fi

if check_tool "Nexus" "http://ai-nexus:8081/service/rest/v1/status"; then
    setup_nexus
fi

if check_tool "Jenkins" "http://jenkins-master:8080/jenkins/login"; then
    setup_jenkins
fi

echo ""
echo "============================================================"
echo "  RBAC Initialization Complete"
echo "============================================================"
echo ""
echo "Groups created in: GitLab, Gitea, SonarQube, Nexus"
echo "  - devops-readonly  : View/browse only"
echo "  - devops-readwrite : Create, modify, build"
echo "  - devops-admin     : Full administrative access"
echo ""
echo "Service account: ${SVC_USER}"
echo "  Credentials stored at: secret/service-accounts/{tool}"
echo ""
echo "To onboard a user, add them to the appropriate group in each tool."
echo "============================================================"
