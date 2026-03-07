#!/bin/sh
# vault-init.sh — initializes Vault, unseals, seeds all tool credentials.
# On first run: full init + unseal + seed. On subsequent runs: unseal only.
# NOTE: Do NOT use "set -e" — vault status returns exit code 2 when sealed

echo "=== Vault Initialization (Persistent Mode) ==="
echo "Waiting for Vault server to be reachable..."

until vault status -format=json >/dev/null 2>&1; do
    STATUS_CODE=$?
    if [ "$STATUS_CODE" = "2" ] || [ "$STATUS_CODE" = "1" ]; then
        break
    fi
    echo "Vault not ready, waiting..."
    sleep 2
done
sleep 1

INIT_FILE="/vault/file/.vault-initialized"

INIT_STATUS=$(vault status -format=json 2>/dev/null || true)
INITIALIZED=$(echo "$INIT_STATUS" | grep '"initialized"' | awk '{print $2}' | tr -d ',')
SEALED=$(echo "$INIT_STATUS" | grep '"sealed"' | awk '{print $2}' | tr -d ',')

echo "Vault status: initialized=$INITIALIZED, sealed=$SEALED"

if [ "$INITIALIZED" = "false" ]; then
    echo "First run — initializing Vault with 1 key share, threshold 1..."

    apk add --no-cache jq >/dev/null 2>&1 || true

    INIT_OUTPUT=$(vault operator init -key-shares=1 -key-threshold=1 -format=json)

    UNSEAL_KEY=$(echo "$INIT_OUTPUT" | jq -r '.unseal_keys_b64[0]')
    ROOT_TOKEN=$(echo "$INIT_OUTPUT" | jq -r '.root_token')

    echo "Vault initialized."
    echo "Root token: ${ROOT_TOKEN}"

    echo "$UNSEAL_KEY" > /vault/file/.unseal-key
    echo "$ROOT_TOKEN" > /vault/file/.root-token
    chmod 600 /vault/file/.unseal-key /vault/file/.root-token

    vault operator unseal "$UNSEAL_KEY"
    echo "Vault unsealed."

    export VAULT_TOKEN="$ROOT_TOKEN"

    vault secrets enable -path=secret kv-v2 2>/dev/null || echo "KV-v2 already enabled"

elif [ "$INITIALIZED" = "true" ]; then
    echo "Vault already initialized."

    if [ "$SEALED" = "true" ]; then
        if [ -f /vault/file/.unseal-key ]; then
            UNSEAL_KEY=$(cat /vault/file/.unseal-key)
            vault operator unseal "$UNSEAL_KEY"
            echo "Vault unsealed."
        else
            echo "ERROR: Vault is sealed but no unseal key found!"
            exit 1
        fi
    else
        echo "Vault is already unsealed."
    fi

    if [ -f /vault/file/.root-token ]; then
        export VAULT_TOKEN=$(cat /vault/file/.root-token)
    fi

else
    echo "ERROR: Could not determine Vault initialization status"
    exit 1
fi

set -e

if [ -f "$INIT_FILE" ]; then
    echo "Secrets already seeded. Skipping."
    echo "=== Vault ready ==="
    exit 0
fi

echo "=== Seeding secrets (first time) ==="

if [ -n "$GITLAB_PAT" ]; then
    vault kv put secret/gitlab token="$GITLAB_PAT" username="root" password="${GITLAB_ROOT_PASSWORD:-OHphO3nIQxoSOA5nuxITXal6OdSbTnLevUg5LZKGJSs=}"
else
    vault kv put secret/gitlab token="" username="root" password="${GITLAB_ROOT_PASSWORD:-OHphO3nIQxoSOA5nuxITXal6OdSbTnLevUg5LZKGJSs=}"
fi

vault kv put secret/gitea token="dbfd7723057682c2ce99a0fc5177f9f7660d68f6" username="${GITEA_ADMIN_USER:-admin}" password="${GITEA_ADMIN_PASSWORD:-admin123}"
vault kv put secret/sonarqube password='N7@qL9!fR2#XwA8$' token=""
vault kv put secret/nexus username="admin" password="r"
vault kv put secret/jenkins username="admin" password="admin123" git_token="dbfd7723057682c2ce99a0fc5177f9f7660d68f6"
vault kv put secret/splunk token=""
vault kv put secret/jira username="" api_token=""
vault kv put secret/terraform git_token="dbfd7723057682c2ce99a0fc5177f9f7660d68f6"
vault kv put secret/terraform/vsphere server="" user="" password=""
vault kv put secret/terraform/azure subscription_id="" client_id="" client_secret="" tenant_id=""
vault kv put secret/terraform/aws access_key="" secret_key=""
vault kv put secret/openai api_key=""

echo "Admin secrets seeded."

vault policy write devops-readonly - <<'POLICY'
path "secret/data/*" { capabilities = ["read", "list"] }
path "secret/metadata/*" { capabilities = ["read", "list"] }
POLICY

vault policy write devops-readwrite - <<'POLICY'
path "secret/data/*" { capabilities = ["create", "read", "update", "list"] }
path "secret/metadata/*" { capabilities = ["read", "list"] }
POLICY

vault policy write devops-admin - <<'POLICY'
path "secret/*" { capabilities = ["create", "read", "update", "delete", "list", "sudo"] }
path "sys/policies/*" { capabilities = ["read", "list"] }
path "auth/*" { capabilities = ["create", "read", "update", "delete", "list"] }
path "identity/*" { capabilities = ["create", "read", "update", "delete", "list"] }
POLICY

vault auth enable approle 2>/dev/null || echo "AppRole already enabled"
vault write auth/approle/role/devops-backend token_policies="devops-readwrite" token_ttl=24h token_max_ttl=48h secret_id_ttl=0

ROLE_ID=$(vault read -field=role_id auth/approle/role/devops-backend/role-id)
SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/devops-backend/secret-id)
vault kv put secret/service-accounts/vault role_id="$ROLE_ID" secret_id="$SECRET_ID"

vault write identity/group name="devops-readonly" policies="devops-readonly" type="internal" 2>/dev/null || true
vault write identity/group name="devops-readwrite" policies="devops-readwrite" type="internal" 2>/dev/null || true
vault write identity/group name="devops-admin" policies="devops-admin" type="internal" 2>/dev/null || true

for tool in gitlab gitea sonarqube nexus jenkins; do
    if ! vault kv get "secret/service-accounts/${tool}" >/dev/null 2>&1; then
        vault kv put "secret/service-accounts/${tool}" token="" username="svc-devops-backend" password=""
    fi
done

touch "$INIT_FILE"

echo "=== Vault initialization complete ==="
echo "Root token: /vault/file/.root-token"
