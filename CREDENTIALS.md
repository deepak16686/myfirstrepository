# Infrastructure Stack Credentials
> **All credentials are stored in HashiCorp Vault.**
> Vault UI: http://localhost:8200/ui | Root Token: see Vault volume `/vault/file/.root-token`
> Last verified: 2026-03-12

---

## Credential Status Overview

| # | Service | Status | URL | Username | Password/Token |
|---|---------|--------|-----|----------|----------------|
| 1 | HashiCorp Vault | ✅ Healthy | http://localhost:8200 | root token | see below |
| 2 | GitLab | ✅ Working | http://localhost:8929/gitlab | root | see Vault: `secret/gitlab` |
| 3 | Gitea | ✅ Working | http://localhost:3002 | admin | see Vault: `secret/gitea` |
| 4 | Jenkins | ✅ Working | http://localhost:8080/jenkins | admin | see Vault: `secret/jenkins` |
| 5 | SonarQube | ✅ Working | http://localhost:9002 | admin | see Vault: `secret/sonarqube` |
| 6 | Nexus | ✅ Working | http://localhost:8181 | admin | see Vault: `secret/nexus` |
| 7 | Splunk | ✅ Working | http://localhost:10000/splunk | admin | see Vault: `secret/splunk` |
| 8 | Grafana | ✅ Working | http://localhost:3000 | admin | see Vault: `secret/grafana` |
| 9 | MinIO | ✅ Working | http://localhost:9001 | admin | see Vault: `secret/minio` |
| 10 | Jira | ✅ Fixed | http://localhost:8180 | deepak16686 | see Vault: `secret/jira` |
| 11 | Redmine | ✅ Working | http://localhost:8090 | admin | see Vault: `secret/redmine` |
| 12 | PostgreSQL | ✅ Working | localhost:5432 | platform | see Vault: `secret/postgres` |
| 13 | Redis | ✅ Working | localhost:6379 | — | no auth |
| 14 | Prometheus | ✅ Working | http://localhost:9090 | — | no auth |
| 15 | Jaeger | ✅ Working | http://localhost:16686 | — | no auth |
| 16 | ChromaDB | ✅ Working | http://localhost:8005 | — | no auth (use /api/v2/) |
| 17 | Qdrant | ✅ Working | http://localhost:6333 | — | no auth |
| 18 | MailHog | ✅ Working | http://localhost:8025 | — | no auth |

---

## 1. HashiCorp Vault (Secret Store)

| Field | Value |
|-------|-------|
| **UI** | http://localhost:8200/ui |
| **API** | http://localhost:8200 |
| **Root Token** | Stored in Docker volume: `docker exec vault sh -c "cat /vault/file/.root-token"` |
| **Vault Path** | `secret/data/<service>` |
| **Status** | Unsealed, healthy |
| **Auto-unseal** | Yes (vault-unseal sidecar) |

> **Read a secret:** `curl -H "X-Vault-Token: <token>" http://localhost:8200/v1/secret/data/<service>`

---

## 2. GitLab

| Field | Value |
|-------|-------|
| **URL** | http://localhost:8929/gitlab |
| **Username** | `root` |
| **Password** | `xK9#mP2@vL5nQ8!` |
| **Personal Access Token** | `glpat-EBNSrUx_8--10xgpVWHvxG86MQp1OjEH.01.0w0u3pz9o` |
| **API Base** | `http://localhost:8929/gitlab/api/v4` |
| **SSH Port** | 2224 |
| **Vault Path** | `secret/data/gitlab` |
| **Note** | External URL: `https://devstack.deepaksharma.live/gitlab` (use localhost for internal) |

```bash
# Test: curl -H "PRIVATE-TOKEN: glpat-EBNSrUx_8--10xgpVWHvxG86MQp1OjEH.01.0w0u3pz9o" http://localhost:8929/gitlab/api/v4/version
```

---

## 3. Gitea

| Field | Value |
|-------|-------|
| **URL** | http://localhost:3002 |
| **Username** | `admin` |
| **Password** | `admin123` |
| **API Token** | `dbfd7723057682c2ce99a0fc5177f9f7660d68f6` |
| **API Base** | `http://localhost:3002/api/v1` |
| **SSH Port** | 2222 |
| **Jenkins Org** | `jenkins-projects` |
| **GitHub Actions Org** | `github-projects` |
| **Vault Path** | `secret/data/gitea` |

```bash
# Test: curl -H "Authorization: token dbfd7723057682c2ce99a0fc5177f9f7660d68f6" http://localhost:3002/api/v1/user
```

---

## 4. Jenkins

| Field | Value |
|-------|-------|
| **URL** | http://localhost:8080/jenkins |
| **Username** | `admin` |
| **Password** | `admin123` |
| **API Base** | `http://localhost:8080/jenkins/api/json` |
| **Agents** | `jenkins-agent-1`, `jenkins-agent-2`, `jenkins-agent-3` |
| **Agent Label** | `docker` |
| **Vault Path** | `secret/data/jenkins` |

```bash
# Test: curl -u admin:admin123 http://localhost:8080/jenkins/api/json?tree=jobs[name]
```

---

## 5. SonarQube

| Field | Value |
|-------|-------|
| **URL** | http://localhost:9002 |
| **Username** | `admin` |
| **Password** | `N7@qL9!fR2#XwA8$` |
| **API Token** | `squ_da6749d456c79b2067f2e90f6ee985270fa9bf18` |
| **Version** | 26.1.0 |
| **Vault Path** | `secret/data/sonarqube` |

```bash
# Test: curl -u "admin:N7@qL9\!fR2#XwA8\$" http://localhost:9002/api/system/status
# API: curl -H "Authorization: Bearer squ_da6749d456c79b2067f2e90f6ee985270fa9bf18" http://localhost:9002/api/projects/search
```

---

## 6. Nexus Repository

| Field | Value |
|-------|-------|
| **UI** | http://localhost:8181 |
| **Username** | `admin` |
| **Password** | `r` |
| **Docker Registry** | `localhost:5001` (host) / `ai-nexus:5001` (containers) |
| **Vault Path** | `secret/data/nexus` |

```bash
# Test: curl -u admin:r http://localhost:8181/service/rest/v1/repositories
# Docker login: docker login localhost:5001 -u admin -p r
```

---

## 7. Splunk

| Field | Value |
|-------|-------|
| **URL** | http://localhost:10000/splunk |
| **Username** | `admin` |
| **Password** | `Admin@1234` |
| **REST API** | `http://localhost:10000/splunk/en-US/splunkd/__raw/services` |
| **HEC Port** | 8088 |
| **Vault Path** | `secret/data/splunk` |

```bash
# Test login: curl -X POST http://localhost:10000/splunk/en-US/splunkd/__raw/services/auth/login -d "username=admin&password=Admin%401234&output_mode=json"
```

---

## 8. Grafana

| Field | Value |
|-------|-------|
| **URL** | http://localhost:3000 |
| **Username** | `admin` |
| **Password** | `admin123` |
| **Vault Path** | `secret/data/grafana` |

```bash
# Test: curl -u admin:admin123 http://localhost:3000/api/org
```

---

## 9. MinIO

| Field | Value |
|-------|-------|
| **UI** | http://localhost:9001 |
| **API** | http://localhost:9000 |
| **Access Key** | `admin` |
| **Secret Key** | `admin123` |
| **Vault Path** | `secret/data/minio` |

```bash
# Test: curl http://localhost:9000/minio/health/live
# mc alias set local http://localhost:9000 admin admin123
```

---

## 10. Jira

| Field | Value |
|-------|-------|
| **URL** | http://localhost:8180 |
| **Username** | `deepak16686` |
| **Password** | `admin123` |
| **Email** | `deepakdce2009@gmail.com` |
| **Groups** | `jira-administrators`, `jira-software-users` |
| **DB** | `jira-postgres` — `jira/jira123@jiradb` |
| **Vault Path** | `secret/data/jira` |
| **Note** | Jira 9+ disables HTTP Basic Auth for REST API by default. UI login works fine. For REST API: generate a PAT at http://localhost:8180/secure/ViewProfile.jspa → Personal Access Tokens → Create Token |

---

## 11. Redmine

| Field | Value |
|-------|-------|
| **URL** | http://localhost:8090 |
| **Username** | `admin` |
| **Password** | `Admin@1234` |
| **API Key** | `701b636febd66b8335cc485b671c27984d31a10b` |
| **Vault Path** | `secret/data/redmine` |

```bash
# Test: curl -H "X-Redmine-API-Key: 701b636febd66b8335cc485b671c27984d31a10b" http://localhost:8090/users/current.json
```

---

## 12. PostgreSQL (Main)

| Field | Value |
|-------|-------|
| **Host** | `localhost:5432` |
| **Username** | `platform` |
| **Password** | `platform123` |
| **Database** | `modernization_platform` |
| **Connection String** | `postgresql://platform:platform123@localhost:5432/modernization_platform` |
| **Taskflow User** | `taskflow` — owns `taskflow_auth`, `taskflow_tasks` databases |
| **Vault Path** | `secret/data/postgres` |

```bash
# Test: docker exec ai-postgres psql -U platform -d modernization_platform -c "\l"
```

### Database Credentials by Service

| Container | DB User | DB Password | Database |
|-----------|---------|-------------|----------|
| `jira-postgres` | `jira` | `jira123` | `jiradb` |
| `ai-sonar-db` | `sonar` | `sonarpass` | `sonarqube` |
| `redmine-db` | `redmine` | `redmine123` | `redmine` |
| `ai-postgres` | `platform` | `platform123` | `modernization_platform` |

---

## 13–18. No-Auth Services

| Service | URL | Notes |
|---------|-----|-------|
| **Redis** | `localhost:6379` | No password configured |
| **Prometheus** | http://localhost:9090/prometheus/ | No auth — health: `/prometheus/-/healthy`, API: `/prometheus/api/v1/` |
| **Jaeger** | http://localhost:16686 | No auth |
| **ChromaDB** | http://localhost:8005 | No auth — use `/api/v2/` (v1 deprecated) |
| **Qdrant** | http://localhost:6333 | No auth |
| **MailHog** | http://localhost:8025 | No auth — SMTP on port 1025 (internal) |

---

## Taskflow Microservices

| Service | URL | Health |
|---------|-----|--------|
| **API Gateway** | http://localhost:18080 | `/health` |
| **Auth Service** | http://localhost:18081 | `/health` |
| **Task Service** | http://localhost:18082 | `/health` |
| **Notification Service** | http://localhost:18083 | `/health` |

---

## Observability Stack

| Service | URL | Notes |
|---------|-----|-------|
| **Grafana** | http://localhost:3000 | admin/admin123 |
| **Prometheus** | http://localhost:9090 | No auth |
| **Loki** | http://localhost:3100 | No auth (internal) |
| **Jaeger** | http://localhost:16686 | No auth |
| **cAdvisor** | http://localhost:8182 | No auth |
| **Node Exporter** | http://localhost:9100 | No auth |
| **DCGM Exporter** | http://localhost:9400 | No auth |

---

## AI / ML Services

| Service | URL | Notes |
|---------|-----|-------|
| **Ollama** | http://localhost:11434 | No auth |
| **ChromaDB** | http://localhost:8005 | No auth, use `/api/v2/` |
| **Qdrant** | http://localhost:6333 | No auth |
| **ChromaDB Admin** | http://localhost:3001 | No auth (ARM image — may restart) |

---

## Vault Quick Reference

```bash
# Get root token
VAULT_TOKEN=$(docker exec vault sh -c "cat /vault/file/.root-token")

# Read any secret
curl -H "X-Vault-Token: $VAULT_TOKEN" http://localhost:8200/v1/secret/data/<service>

# Available secret paths:
# secret/data/gitlab      → GitLab root credentials + PAT
# secret/data/gitea       → Gitea admin credentials + API token
# secret/data/jenkins     → Jenkins admin credentials
# secret/data/sonarqube   → SonarQube admin credentials + API token
# secret/data/nexus       → Nexus admin credentials
# secret/data/splunk      → Splunk admin credentials
# secret/data/jira        → Jira admin credentials
# secret/data/redmine     → Redmine admin credentials + API key
# secret/data/minio       → MinIO access key + secret key
# secret/data/postgres    → PostgreSQL credentials
# secret/data/grafana     → Grafana admin credentials
# secret/data/vault       → Vault root token reference
```

---

## Port Map

```
Port  | Service                    Port  | Service
------|----------------------------+------+---------------------------
3000  | Grafana                    9000  | MinIO API
3001  | ChromaDB Admin             9001  | MinIO UI
3002  | Gitea                      9002  | SonarQube
3100  | Loki                       9090  | Prometheus
5432  | PostgreSQL                 9100  | Node Exporter
6333  | Qdrant                     9400  | DCGM Exporter
6334  | Qdrant gRPC               10000  | Splunk
6379  | Redis                     11434  | Ollama
8005  | ChromaDB                  14268  | Jaeger (collector)
8025  | MailHog                   16686  | Jaeger UI
8080  | Jenkins                   18080  | Taskflow API Gateway
8088  | Splunk HEC                18081  | Taskflow Auth Service
8090  | Redmine                   18082  | Taskflow Task Service
8180  | Jira                      18083  | Taskflow Notification
8181  | Nexus UI                   2222  | Gitea SSH
8182  | cAdvisor                   2224  | GitLab SSH
8183  | Trivy Server               5001  | Nexus Docker Registry
8200  | Vault                      8443  | Nginx Proxy
8929  | GitLab
```
