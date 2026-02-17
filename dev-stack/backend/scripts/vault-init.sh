#!/bin/sh
set -e

echo "=== Vault Secret Initialization ==="
echo "Waiting for Vault to be ready..."

until vault status 2>/dev/null; do
    echo "Vault not ready, waiting..."
    sleep 2
done

echo "Vault is ready. Seeding secrets..."

# ============================================================
# 1. Admin credentials (used by rbac-init to bootstrap tools)
# ============================================================

# GitLab - admin credentials (root user)
if [ -n "$GITLAB_PAT" ]; then
    vault kv put secret/gitlab \
        token="$GITLAB_PAT" \
        username="root" \
        password="${GITLAB_ROOT_PASSWORD:-OHphO3nIQxoSOA5nuxITXal6OdSbTnLevUg5LZKGJSs=}"
    echo "GitLab admin credentials stored from environment"
else
    if ! vault kv get secret/gitlab >/dev/null 2>&1; then
        vault kv put secret/gitlab \
            token="" \
            username="root" \
            password="${GITLAB_ROOT_PASSWORD:-OHphO3nIQxoSOA5nuxITXal6OdSbTnLevUg5LZKGJSs=}"
        echo "GitLab credentials created (set token via: docker exec -e VAULT_TOKEN=dev-root-token vault vault kv put secret/gitlab token=glpat-xxx username=root password=YOUR_PASSWORD)"
    else
        echo "GitLab credentials already exist in Vault, skipping"
    fi
fi

# Gitea - admin credentials (used as GITHUB_TOKEN and JENKINS_GIT_TOKEN)
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

# Terraform Cloud Providers (empty placeholders)
vault kv put secret/terraform/vsphere \
    server="" \
    user="" \
    password=""

vault kv put secret/terraform/azure \
    subscription_id="" \
    client_id="" \
    client_secret="" \
    tenant_id=""

vault kv put secret/terraform/aws \
    access_key="" \
    secret_key=""

# OpenAI
vault kv put secret/openai \
    api_key=""

echo "Admin secrets seeded."

# ============================================================
# 2. Vault Policies (3 access levels)
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
# 3. AppRole Auth (for service accounts)
# ============================================================

echo ""
echo "=== Configuring AppRole Auth ==="

vault auth enable approle 2>/dev/null || echo "AppRole already enabled"

# Backend service role - readwrite access
vault write auth/approle/role/devops-backend \
    token_policies="devops-readwrite" \
    token_ttl=24h \
    token_max_ttl=48h \
    secret_id_ttl=0

ROLE_ID=$(vault read -field=role_id auth/approle/role/devops-backend/role-id)
SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/devops-backend/secret-id)

echo "AppRole 'devops-backend' created (role_id: ${ROLE_ID})"

# Store AppRole credentials so backend can use them
vault kv put secret/service-accounts/vault \
    role_id="$ROLE_ID" \
    secret_id="$SECRET_ID"

# ============================================================
# 4. Vault Identity Groups
# ============================================================

echo ""
echo "=== Creating Identity Groups ==="

vault write identity/group name="devops-readonly" policies="devops-readonly" type="internal" 2>/dev/null || echo "Group devops-readonly exists"
vault write identity/group name="devops-readwrite" policies="devops-readwrite" type="internal" 2>/dev/null || echo "Group devops-readwrite exists"
vault write identity/group name="devops-admin" policies="devops-admin" type="internal" 2>/dev/null || echo "Group devops-admin exists"

echo "Identity groups created."

# ============================================================
# 5. Service account placeholders (populated by rbac-init)
# ============================================================

echo ""
echo "=== Creating service account placeholders ==="

# Only create if they don't exist yet (rbac-init populates real values)
for tool in gitlab gitea sonarqube nexus jenkins; do
    if ! vault kv get "secret/service-accounts/${tool}" >/dev/null 2>&1; then
        vault kv put "secret/service-accounts/${tool}" token="" username="svc-devops-backend" password=""
        echo "Placeholder: secret/service-accounts/${tool}"
    else
        echo "Already exists: secret/service-accounts/${tool}"
    fi
done

echo ""
echo "=== Vault initialization complete ==="
echo "Admin secrets: gitlab, gitea, sonarqube, nexus, jenkins, splunk, jira, terraform, openai"
echo "Policies: devops-readonly, devops-readwrite, devops-admin"
echo "AppRole: devops-backend (role_id stored at secret/service-accounts/vault)"
echo "Service account placeholders: gitlab, gitea, sonarqube, nexus, jenkins"
