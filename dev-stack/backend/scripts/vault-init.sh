#!/bin/sh
# File: vault-init.sh
# Purpose: Initializes HashiCorp Vault on first run — generates unseal key + root token, unseals,
#          enables KV-v2 secrets engine, seeds all tool credentials (GitLab, Gitea, SonarQube, Nexus,
#          Jenkins, Splunk, Jira, Terraform, OpenAI), creates RBAC policies, and sets up AppRole auth.
# When Used: Runs as the 'vault-init' container at stack startup. On first run, performs full
#            initialization and seeding. On subsequent runs, only unseals Vault (skips seeding if
#            marker file /vault/file/.vault-initialized exists). Stores tokens persistently on the
#            vault-data volume so they survive container restarts.
# Why Created: Automates the entire Vault setup so the dev-stack comes up with all secrets pre-loaded
#              and the backend can immediately read credentials without manual Vault configuration.
#              Uses persistent file storage mode so secrets survive across docker compose down/up cycles.
# NOTE: Do NOT use "set -e" — vault status returns exit code 2 when sealed

echo "=== Vault Initialization (Persistent Mode) ==="
echo "Waiting for Vault server to be reachable..."

# Wait until Vault API is listening (even if sealed/uninitialized)
until vault status -format=json >/dev/null 2>&1; do
    # vault status exits 2 when sealed, 1 when error — both mean API is up
    STATUS_CODE=$?
    if [ "$STATUS_CODE" = "2" ] || [ "$STATUS_CODE" = "1" ]; then
        break
    fi
    echo "Vault not ready, waiting..."
    sleep 2
done
sleep 1

INIT_FILE="/vault/file/.vault-initialized"

# ============================================================
# STEP 1: Initialize Vault (first run only)
# ============================================================

# Parse JSON status robustly using grep on separate lines
INIT_STATUS=$(vault status -format=json 2>/dev/null || true)
INITIALIZED=$(echo "$INIT_STATUS" | grep '"initialized"' | awk '{print $2}' | tr -d ',')
SEALED=$(echo "$INIT_STATUS" | grep '"sealed"' | awk '{print $2}' | tr -d ',')

echo "Vault status: initialized=$INITIALIZED, sealed=$SEALED"

if [ "$INITIALIZED" = "false" ]; then
    echo "First run — initializing Vault with 1 key share, threshold 1..."

    # Install jq for reliable JSON parsing
    apk add --no-cache jq >/dev/null 2>&1 || true

    INIT_OUTPUT=$(vault operator init -key-shares=1 -key-threshold=1 -format=json)

    UNSEAL_KEY=$(echo "$INIT_OUTPUT" | jq -r '.unseal_keys_b64[0]')
    ROOT_TOKEN=$(echo "$INIT_OUTPUT" | jq -r '.root_token')

    echo "Vault initialized."
    echo "Root token: ${ROOT_TOKEN}"

    # Persist the unseal key + root token for future restarts
    echo "$UNSEAL_KEY" > /vault/file/.unseal-key
    echo "$ROOT_TOKEN" > /vault/file/.root-token
    chmod 600 /vault/file/.unseal-key /vault/file/.root-token

    # Unseal
    vault operator unseal "$UNSEAL_KEY"
    echo "Vault unsealed."

    # Use the generated root token for subsequent operations
    export VAULT_TOKEN="$ROOT_TOKEN"

    # Enable KV-v2 secrets engine
    vault secrets enable -path=secret kv-v2 2>/dev/null || echo "KV-v2 already enabled"

elif [ "$INITIALIZED" = "true" ]; then
    echo "Vault already initialized."

    # Unseal if sealed
    if [ "$SEALED" = "true" ]; then
        if [ -f /vault/file/.unseal-key ]; then
            UNSEAL_KEY=$(cat /vault/file/.unseal-key)
            vault operator unseal "$UNSEAL_KEY"
            echo "Vault unsealed."
        else
            echo "ERROR: Vault is sealed but no unseal key found at /vault/file/.unseal-key!"
            exit 1
        fi
    else
        echo "Vault is already unsealed."
    fi

    # Use stored root token
    if [ -f /vault/file/.root-token ]; then
        export VAULT_TOKEN=$(cat /vault/file/.root-token)
    fi

else
    echo "ERROR: Could not determine Vault initialization status"
    echo "Status output: $INIT_STATUS"
    exit 1
fi

# From here on, fail on errors
set -e

# ============================================================
# STEP 2: Seed secrets (only if not already seeded)
# ============================================================

if [ -f "$INIT_FILE" ]; then
    echo ""
    echo "Secrets already seeded (found $INIT_FILE). Skipping seed."
    echo "To re-seed, delete $INIT_FILE and restart vault-init."
    echo ""
    echo "=== Vault ready ==="
    exit 0
fi

echo ""
echo "=== Seeding secrets (first time) ==="

# GitLab - admin credentials (root user)
if [ -n "$GITLAB_PAT" ]; then
    vault kv put secret/gitlab \
        token="$GITLAB_PAT" \
        username="root" \
        password="${GITLAB_ROOT_PASSWORD:-OHphO3nIQxoSOA5nuxITXal6OdSbTnLevUg5LZKGJSs=}"
    echo "GitLab admin credentials stored (token from GITLAB_PAT env)"
else
    vault kv put secret/gitlab \
        token="" \
        username="root" \
        password="${GITLAB_ROOT_PASSWORD:-OHphO3nIQxoSOA5nuxITXal6OdSbTnLevUg5LZKGJSs=}"
    echo "GitLab credentials stored (token EMPTY - set via: vault kv put secret/gitlab token=glpat-xxx ...)"
fi

# Gitea
vault kv put secret/gitea \
    token="dbfd7723057682c2ce99a0fc5177f9f7660d68f6" \
    username="${GITEA_ADMIN_USER:-admin}" \
    password="${GITEA_ADMIN_PASSWORD:-admin123}"

# SonarQube
vault kv put secret/sonarqube \
    password='N7@qL9!fR2#XwA8$' \
    token=""

# Nexus
vault kv put secret/nexus \
    username="admin" \
    password="r"

# Jenkins
vault kv put secret/jenkins \
    username="admin" \
    password="admin123" \
    git_token="dbfd7723057682c2ce99a0fc5177f9f7660d68f6"

# Splunk
vault kv put secret/splunk \
    token=""

# Jira
vault kv put secret/jira \
    username="" \
    api_token=""

# Terraform
vault kv put secret/terraform \
    git_token="dbfd7723057682c2ce99a0fc5177f9f7660d68f6"

vault kv put secret/terraform/vsphere \
    server="" user="" password=""

vault kv put secret/terraform/azure \
    subscription_id="" client_id="" client_secret="" tenant_id=""

vault kv put secret/terraform/aws \
    access_key="" secret_key=""

# OpenAI
vault kv put secret/openai \
    api_key=""

echo "Admin secrets seeded."

# ============================================================
# 3. Vault Policies (3 access levels)
# ============================================================

echo ""
echo "=== Creating Vault Policies ==="

vault policy write devops-readonly - <<'POLICY'
# Read-only access to all secrets
path "secret/data/*" {
  capabilities = ["read", "list"]
}
path "secret/metadata/*" {
  capabilities = ["read", "list"]
}
POLICY
echo "Policy created: devops-readonly"

vault policy write devops-readwrite - <<'POLICY'
# Read-write access to secrets
path "secret/data/*" {
  capabilities = ["create", "read", "update", "list"]
}
path "secret/metadata/*" {
  capabilities = ["read", "list"]
}
POLICY
echo "Policy created: devops-readwrite"

vault policy write devops-admin - <<'POLICY'
# Full admin access
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
path "sys/policies/*" {
  capabilities = ["read", "list"]
}
path "auth/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "identity/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
POLICY
echo "Policy created: devops-admin"

# ============================================================
# 4. AppRole Auth (for service accounts)
# ============================================================

echo ""
echo "=== Configuring AppRole Auth ==="

vault auth enable approle 2>/dev/null || echo "AppRole already enabled"

vault write auth/approle/role/devops-backend \
    token_policies="devops-readwrite" \
    token_ttl=24h \
    token_max_ttl=48h \
    secret_id_ttl=0

ROLE_ID=$(vault read -field=role_id auth/approle/role/devops-backend/role-id)
SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/devops-backend/secret-id)

echo "AppRole 'devops-backend' created (role_id: ${ROLE_ID})"

vault kv put secret/service-accounts/vault \
    role_id="$ROLE_ID" \
    secret_id="$SECRET_ID"

# ============================================================
# 5. Vault Identity Groups
# ============================================================

echo ""
echo "=== Creating Identity Groups ==="

vault write identity/group name="devops-readonly" policies="devops-readonly" type="internal" 2>/dev/null || echo "Group devops-readonly exists"
vault write identity/group name="devops-readwrite" policies="devops-readwrite" type="internal" 2>/dev/null || echo "Group devops-readwrite exists"
vault write identity/group name="devops-admin" policies="devops-admin" type="internal" 2>/dev/null || echo "Group devops-admin exists"

echo "Identity groups created."

# ============================================================
# 6. Service account placeholders
# ============================================================

echo ""
echo "=== Creating service account placeholders ==="

for tool in gitlab gitea sonarqube nexus jenkins; do
    if ! vault kv get "secret/service-accounts/${tool}" >/dev/null 2>&1; then
        vault kv put "secret/service-accounts/${tool}" token="" username="svc-devops-backend" password=""
        echo "Placeholder: secret/service-accounts/${tool}"
    else
        echo "Already exists: secret/service-accounts/${tool}"
    fi
done

# ============================================================
# Mark as initialized so we don't re-seed on restart
# ============================================================
touch "$INIT_FILE"

echo ""
echo "=== Vault initialization complete ==="
echo "Admin secrets: gitlab, gitea, sonarqube, nexus, jenkins, splunk, jira, terraform, openai"
echo "Policies: devops-readonly, devops-readwrite, devops-admin"
echo "AppRole: devops-backend (role_id stored at secret/service-accounts/vault)"
echo "Service account placeholders: gitlab, gitea, sonarqube, nexus, jenkins"
echo ""
echo "Secrets are PERSISTENT — they survive Vault restarts."
echo "Root token stored at: /vault/file/.root-token"
