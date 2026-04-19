# Secret Rotation Runbook

Authoritative rotation procedures for every secret used by the DevOps platform.
Applies to: GitLab PAT, SonarQube admin/password & project tokens, Nexus password,
Splunk admin/HEC token, Redmine API key, Postgres passwords (AI / Sonar / Redmine),
MinIO root, Grafana admin, Vault token.

**All secrets live in HashiCorp Vault under `secret/devops/<tool>`.**
Never commit real values; see `.env.example` at repo root for the schema.

---

## 0. Vault conventions

Paths (KV v2):

| Tool            | Vault path                                 | Fields                                  |
|-----------------|--------------------------------------------|-----------------------------------------|
| GitLab          | `secret/devops/gitlab`                     | `pat`, `root_password`, `runner_token`  |
| Nexus           | `secret/devops/nexus`                      | `username`, `password`                  |
| SonarQube       | `secret/devops/sonarqube`                  | `username`, `password`, `global_token`  |
| SonarQube proj  | `secret/devops/sonarqube/<project-key>`    | `token`                                 |
| Splunk          | `secret/devops/splunk`                     | `admin_password`, `hec_token`           |
| Redmine         | `secret/devops/redmine`                    | `admin_password`, `api_key`, `secret_key_base` |
| Postgres AI     | `secret/devops/postgres-ai`                | `user`, `password`, `db`                |
| MinIO           | `secret/devops/minio`                      | `root_user`, `root_password`            |
| Grafana         | `secret/devops/grafana`                    | `admin_password`                        |

Read into shell:

```bash
export GITLAB_TOKEN=$(vault kv get -field=pat secret/devops/gitlab)
export NEXUS_PASSWORD=$(vault kv get -field=password secret/devops/nexus)
export SONARQUBE_PASSWORD=$(vault kv get -field=password secret/devops/sonarqube)
```

K8s (via External Secrets Operator — example for Sonar):

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: sonarqube-admin
  namespace: devops
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: sonarqube-admin
  data:
    - secretKey: password
      remoteRef:
        key: secret/devops/sonarqube
        property: password
```

---

## 1. GitLab Personal Access Token (PAT)

**Rotate every 90 days.** Three PATs require IMMEDIATE rotation (see list at bottom).

### 1a. Revoke the old PAT (UI)

1. Open GitLab -> top-right avatar -> **Preferences** -> **Access Tokens**.
2. Find the active token by name / creation date.
3. Click **Revoke**. This takes effect immediately; all pipelines / tools using it will start failing within seconds.

### 1b. Revoke via API

```bash
# As admin, list tokens for the user (find the id first):
curl -sSf -H "PRIVATE-TOKEN: $GITLAB_ADMIN_TOKEN" \
  "${GITLAB_URL}/api/v4/personal_access_tokens?user_id=1" | jq '.[] | {id, name, active, created_at}'

# Then revoke:
curl -sSf -X DELETE -H "PRIVATE-TOKEN: $GITLAB_ADMIN_TOKEN" \
  "${GITLAB_URL}/api/v4/personal_access_tokens/<id>"
```

### 1c. Mint a new PAT

UI: **Access Tokens** -> **Add new token**.

Required scopes for this platform:
- `api`               (pipeline workflow + repo listing)
- `read_repository`   (clone via HTTP)
- `write_repository`  (commit generated `.gitlab-ci.yml` / `Dockerfile`)
- `read_registry`, `write_registry` (only if pushing to GitLab Container Registry)

Set **expiration** = today + 90 days.

### 1d. Store in Vault

```bash
vault kv put secret/devops/gitlab \
  pat="<new-glpat-value>" \
  expires_at="$(date -u -d '+90 days' +%Y-%m-%dT%H:%M:%SZ)"
```

### 1e. Re-deploy consumers

```bash
# Kubernetes (ESO will pick up within refreshInterval; force it now):
kubectl -n devops annotate externalsecret gitlab-pat force-sync="$(date +%s)" --overwrite

# Compose (restart services to re-read .env):
docker compose --env-file .env up -d --force-recreate backend

# Open WebUI function (update via sqlite or re-install the function):
python devops-tools-backend/openwebui_tools/install.py  # re-reads GITLAB_TOKEN
```

### 1f. Verify

```bash
curl -sSf -H "PRIVATE-TOKEN: $GITLAB_TOKEN" "${GITLAB_URL}/api/v4/user" \
  | jq '{id, username, name}'
```

---

## 2. SonarQube admin password

### 2a. Rotate

```bash
# Login as admin, change password via API:
curl -sSf -u "admin:<OLD_PASSWORD>" \
  -X POST "${SONARQUBE_URL}/api/users/change_password" \
  -d "login=admin&previousPassword=<OLD_PASSWORD>&password=<NEW_PASSWORD>"
```

### 2b. Persist

```bash
vault kv put secret/devops/sonarqube password="<NEW_PASSWORD>" rotated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

### 2c. Verify

```bash
curl -sSf -u "admin:$(vault kv get -field=password secret/devops/sonarqube)" \
  "${SONARQUBE_URL}/api/system/status" | jq '.status'
# Expect: "UP"
```

---

## 3. SonarQube project analysis tokens (bulk)

There are 20 legacy-migration project tokens: `SONAR_TOKEN_LEGACY_<PROJECT>`
(see `sonarqube-projects.md` for the full list).

### 3a. Rotate one

```bash
# Revoke (use the token name, not the value):
curl -sSf -u "admin:$SONARQUBE_PASSWORD" \
  -X POST "${SONARQUBE_URL}/api/user_tokens/revoke" \
  -d "name=legacy-banking-core-ci"

# Generate new (project-scoped):
NEW_TOKEN=$(curl -sSf -u "admin:$SONARQUBE_PASSWORD" \
  -X POST "${SONARQUBE_URL}/api/user_tokens/generate" \
  -d "name=legacy-banking-core-ci&type=PROJECT_ANALYSIS_TOKEN&projectKey=legacy-banking-core" \
  | jq -r '.token')

# Persist:
vault kv put secret/devops/sonarqube/legacy-banking-core token="$NEW_TOKEN"
```

### 3b. Rotate all 20 (script)

```bash
for project in asset_management authentication_service banking_core crm_system \
               data_warehouse document_archive email_gateway erp_finance \
               flight_reservation healthcare_records hotel_booking hr_payroll \
               insurance_policy inventory_manager logistics_tracker \
               manufacturing_mes reporting_engine retail_pos supply_chain \
               telecom_billing; do
  key="legacy-${project//_/-}"
  name="${key}-ci"
  curl -sSf -u "admin:$SONARQUBE_PASSWORD" \
    -X POST "${SONARQUBE_URL}/api/user_tokens/revoke" -d "name=${name}" || true
  NEW=$(curl -sSf -u "admin:$SONARQUBE_PASSWORD" \
    -X POST "${SONARQUBE_URL}/api/user_tokens/generate" \
    -d "name=${name}&type=PROJECT_ANALYSIS_TOKEN&projectKey=${key}" | jq -r '.token')
  vault kv put "secret/devops/sonarqube/${key}" token="$NEW"
  printf 'rotated: %s\n' "$key"
done
```

### 3c. Verify

```bash
curl -sSf -u "$(vault kv get -field=token secret/devops/sonarqube/legacy-banking-core):" \
  "${SONARQUBE_URL}/api/authentication/validate" | jq '.valid'
# Expect: true
```

---

## 4. Nexus password

### 4a. Rotate

```bash
# Via REST (change the admin password):
curl -sSf -u "admin:$OLD_NEXUS_PASSWORD" \
  -X PUT "${NEXUS_URL}/service/rest/v1/security/users/admin/change-password" \
  -H "Content-Type: text/plain" \
  -d "$NEW_NEXUS_PASSWORD"
```

### 4b. Persist

```bash
vault kv put secret/devops/nexus username=admin password="$NEW_NEXUS_PASSWORD"
```

### 4c. Verify

```bash
NEW=$(vault kv get -field=password secret/devops/nexus)
curl -sSf -u "admin:$NEW" "${NEXUS_URL}/service/rest/v1/status" | jq '.'
docker login -u admin -p "$NEW" "${NEXUS_REGISTRY}"
```

---

## 5. Splunk admin password & HEC token

### 5a. Admin password

```bash
# Via splunkd REST:
curl -sSfk -u "admin:$OLD_SPLUNK_PASSWORD" \
  -X POST "${SPLUNK_MGMT_URL}/services/authentication/users/admin" \
  -d "password=$NEW_SPLUNK_PASSWORD"
vault kv put secret/devops/splunk admin_password="$NEW_SPLUNK_PASSWORD"
```

### 5b. HEC token

```bash
# Rotate:
curl -sSfk -u "admin:$NEW_SPLUNK_PASSWORD" \
  -X POST "${SPLUNK_MGMT_URL}/servicesNS/nobody/splunk_httpinput/data/inputs/http/devops-hec" \
  -d "token.rotate=1"

# Retrieve new token:
NEW_HEC=$(curl -sSfk -u "admin:$NEW_SPLUNK_PASSWORD" \
  -X GET "${SPLUNK_MGMT_URL}/servicesNS/nobody/splunk_httpinput/data/inputs/http/devops-hec?output_mode=json" \
  | jq -r '.entry[0].content.token')
vault kv patch secret/devops/splunk hec_token="$NEW_HEC"
```

### 5c. Verify

```bash
curl -sSfk -H "Authorization: Splunk $(vault kv get -field=hec_token secret/devops/splunk)" \
  "${SPLUNK_HEC_URL}/services/collector/health" | jq '.text'
# Expect: "HEC is healthy"
```

---

## 6. Redmine API key & admin password

### 6a. Rotate admin password (Rails console)

```bash
docker exec redmine bundle exec rails runner \
  "u = User.find_by(login: 'admin'); \
   u.password = ENV['NEW_PASSWORD']; \
   u.password_confirmation = ENV['NEW_PASSWORD']; \
   u.must_change_passwd = false; \
   u.save!"
```

### 6b. Rotate API key

```bash
# Via Rails console:
docker exec redmine bundle exec rails runner \
  "u = User.find_by(login: 'admin'); Token.where(user_id: u.id, action: 'api').destroy_all; \
   puts u.api_key"   # this generates and prints the NEW key
```

### 6c. Persist

```bash
vault kv put secret/devops/redmine \
  admin_password="$NEW_PW" \
  api_key="$NEW_API_KEY" \
  secret_key_base="$(openssl rand -hex 64)"
```

### 6d. Verify

```bash
curl -sSf -H "X-Redmine-API-Key: $(vault kv get -field=api_key secret/devops/redmine)" \
  "${REDMINE_URL}/users/current.json" | jq '.user.login'
# Expect: "admin"
```

---

## 7. Postgres passwords (AI / Sonar / Redmine)

### 7a. Rotate inside the DB

```bash
PGPASSWORD="$OLD" psql -h "$POSTGRES_AI_HOST" -U "$POSTGRES_AI_USER" -d "$POSTGRES_AI_DB" \
  -c "ALTER USER \"$POSTGRES_AI_USER\" WITH PASSWORD '$NEW_PW';"
```

### 7b. Persist

```bash
vault kv put secret/devops/postgres-ai user="$POSTGRES_AI_USER" password="$NEW_PW" db="$POSTGRES_AI_DB"
```

### 7c. Verify

```bash
PGPASSWORD="$(vault kv get -field=password secret/devops/postgres-ai)" \
  psql -h "$POSTGRES_AI_HOST" -U "$POSTGRES_AI_USER" -d "$POSTGRES_AI_DB" -c '\q'
echo $?   # Expect: 0
```

---

## 8. MinIO root password

### 8a. Rotate

```bash
mc alias set localminio "${MINIO_URL}" "$MINIO_ROOT_USER" "$OLD_MINIO_ROOT_PASSWORD"
mc admin user password localminio "$MINIO_ROOT_USER" "$NEW_MINIO_ROOT_PASSWORD"
vault kv put secret/devops/minio root_user="$MINIO_ROOT_USER" root_password="$NEW_MINIO_ROOT_PASSWORD"
```

### 8b. Verify

```bash
mc alias set localminio "${MINIO_URL}" "$MINIO_ROOT_USER" \
  "$(vault kv get -field=root_password secret/devops/minio)"
mc admin info localminio
```

---

## 9. Grafana admin password

### 9a. Rotate

```bash
docker exec grafana grafana-cli admin reset-admin-password "$NEW_GRAFANA_PASSWORD"
vault kv put secret/devops/grafana admin_password="$NEW_GRAFANA_PASSWORD"
```

### 9b. Verify

```bash
curl -sSf -u "admin:$(vault kv get -field=admin_password secret/devops/grafana)" \
  "${GRAFANA_URL}/api/health" | jq '.'
```

---

## 10. Vault token

Issue short-lived tokens only. Never use the root token in pipelines.

```bash
# For a CI/CD pipeline that uses AppRole:
vault write -f auth/approle/role/devops-ci role_id=-
ROLE_ID=$(vault read -field=role_id auth/approle/role/devops-ci/role-id)
SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/devops-ci/secret-id)

# In pipeline:
export VAULT_TOKEN=$(vault write -field=token auth/approle/login \
  role_id="$ROLE_ID" secret_id="$SECRET_ID")
```

Revoke a leaked token:

```bash
vault token revoke <leaked-token-accessor>
```

---

## 11. Emergency revoke — all tools

If a laptop is stolen or credentials leak broadly, run:

```bash
./scripts/rotate-all.sh  # (add to scripts/ — wraps the revoke + rotate for every tool above)
```

Minimum manual steps until the script exists:

1. GitLab: revoke all active PATs for user `root` via admin UI.
2. SonarQube: POST `/api/user_tokens/revoke` for every token name.
3. Nexus: change admin password via REST.
4. Splunk: rotate admin password + HEC token.
5. Vault: revoke the compromised approle secret-id.
6. `git filter-repo --invert-paths --path <leaked-file>` if credentials landed in git history, followed by force-push and alerting the team.

---

## 12. Audit trail

Every rotation writes a Vault metadata field `rotated_at`.
A scheduled job (`k8s/cronjob/secret-audit.yaml`) alerts if any secret is older than 90 days.

---

## Current rotation queue (manual action required)

The following credentials were exposed in this repo prior to the remediation pass
and MUST be rotated before any deployment against production GitLab/Nexus/Sonar:

| Secret                                    | Source file (pre-scrub)                          | Status                 |
|-------------------------------------------|--------------------------------------------------|------------------------|
| GitLab PAT A (`glpat-0bUTW...9r7`)        | `fix_pipeline_sonar.py`, `fix_pipeline_tool.py`  | **REVOKE in GitLab UI**|
| GitLab PAT B (`glpat-gZVCe...erv`)        | `create_project_validator_tool.py` (historic)    | **REVOKE in GitLab UI**|
| GitLab PAT C (`glpat-VLnGw...4zy`)        | `.claude/settings.local.json`                    | **REVOKE in GitLab UI**|
| Redmine API key (`701b636feb...1a10b`)    | `create_project_validator_tool.py`               | **REVOKE in Redmine -> My account -> Reset** |
| 20 x SonarQube legacy project tokens      | `sonarqube-projects.md` / `sonarqube-projects.csv` | **Run Section 3b script** |
| Nexus admin password (`admin123` class)   | `fix_pipeline_tool.py`, `files/complete_documentation.md` | **Rotate per Section 4**  |
| SonarQube admin password (`N7@qL9!...A8`) | `sonarqube-projects.md`                          | **Rotate per Section 2**  |
| Grafana admin (`admin123`)                | `monitoring-stack.yml`, `platform-setup/docker-compose.yml` | **Rotate per Section 9**  |
| MinIO root (`minioadmin123`)              | `files/complete_documentation.md`                | **Rotate per Section 8**  |
| Postgres AI (`modernization123`)          | `devops-tools-backend/.env.example`              | **Rotate per Section 7**  |

---

## References

- HashiCorp Vault KV v2: https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2
- External Secrets Operator: https://external-secrets.io/
- GitLab PAT scopes: https://docs.gitlab.com/user/profile/personal_access_tokens
- SonarQube user tokens API: https://next.sonarqube.com/sonarqube/web_api/api/user_tokens
- Nexus REST API: https://help.sonatype.com/repomanager3/integrations/rest-and-integration-api
- Splunk HEC: https://docs.splunk.com/Documentation/Splunk/latest/Data/UsetheHTTPEventCollector
