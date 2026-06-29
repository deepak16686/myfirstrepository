# Infrastructure Stack Credentials
> **All credentials are stored in HashiCorp Vault.**
> Vault UI: Docker Desktop container only (not exposed as a shared portal URL) | Root Token: see Vault volume `/vault/file/.root-token`
> Last verified: 2026-03-12

---

## Credential Status Overview

| # | Service | Status | URL | Username | Password/Token |
|---|---------|--------|-----|----------|----------------|
| 1 | HashiCorp Vault | ✅ Healthy | Docker Desktop container only (not exposed as a shared portal URL) | root token | see below |
| 2 | GitLab | ✅ Working | https://gitlab.deepaksharma.live/gitlab | root | see Vault: `secret/gitlab` |
| 3 | Gitea | ✅ Working | https://gitea.deepaksharma.live | admin | see Vault: `secret/gitea` |
| 4 | Jenkins | ✅ Working | https://jenkins.deepaksharma.live/jenkins | admin | see Vault: `secret/jenkins` |
| 5 | SonarQube | ✅ Working | https://sonarqube.deepaksharma.live | admin | see Vault: `secret/sonarqube` |
| 6 | Nexus | ✅ Working | https://nexus.deepaksharma.live | admin | see Vault: `secret/nexus` |
| 7 | Splunk | ✅ Working | https://splunk.deepaksharma.live/splunk | admin | see Vault: `secret/splunk` |
| 8 | Grafana | ✅ Working | https://grafana.deepaksharma.live | admin | see Vault: `secret/grafana` |
| 9 | MinIO | ✅ Working | https://minio.deepaksharma.live | admin | see Vault: `secret/minio` |
| 10 | Jira | ✅ Fixed | https://jira.deepaksharma.live | deepak16686 | see Vault: `secret/jira` |
| 11 | Redmine | ✅ Working | https://redmine.deepaksharma.live | admin | see Vault: `secret/redmine` |
| 12 | PostgreSQL | ✅ Working | Docker Desktop/container network only | platform | see Vault: `secret/postgres` |
| 13 | Redis | ✅ Working | Docker Desktop/container network only | — | no auth |
| 14 | Prometheus | ✅ Working | https://prometheus.deepaksharma.live | — | no auth |
| 15 | Jaeger | ✅ Working | https://jaeger.deepaksharma.live | — | no auth |
| 16 | ChromaDB | ✅ Working | https://chromadb.deepaksharma.live | — | no auth (use /api/v2/) |
| 17 | Qdrant | ✅ Working | https://qdrant.deepaksharma.live | — | no auth |
| 18 | MailHog | ✅ Working | https://mailhog.deepaksharma.live | — | no auth |

---

## 1. HashiCorp Vault (Secret Store)

| Field | Value |
|-------|-------|
| **UI** | Docker Desktop container only (not exposed as a shared portal URL) |
| **API** | Docker Desktop container only (not exposed as a shared portal URL) |
| **Root Token** | Stored in Docker volume: `docker exec vault sh -c "cat /vault/file/.root-token"` |
| **Vault Path** | `secret/data/<service>` |
| **Status** | Unsealed, healthy |
| **Auto-unseal** | Yes (vault-unseal sidecar) |

> **Read a secret:** use Docker Desktop/container-only Vault access; no shared HTTP URL is published.

---

## 2. GitLab

| Field | Value |
|-------|-------|
| **URL** | https://gitlab.deepaksharma.live/gitlab |
| **Username** | `root` |
| **Password** | `${GITLAB_ROOT_PASSWORD}` |
| **Personal Access Token** | `${GITLAB_TOKEN}` |
| **API Base** | `https://gitlab.deepaksharma.live/gitlab/api/v4` |
| **SSH Port** | 2224 |
| **Vault Path** | `secret/data/gitlab` |
| **Note** | External URL: `https://devstack.deepaksharma.live/gitlab` |

```bash
# Test: curl -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" https://gitlab.deepaksharma.live/gitlab/api/v4/version
```

---

## 3. Gitea

| Field | Value |
|-------|-------|
| **URL** | https://gitea.deepaksharma.live |
| **Username** | `admin` |
| **Password** | `admin123` |
| **API Token** | `${GITEA_TOKEN}` |
| **API Base** | `https://gitea.deepaksharma.live/api/v1` |
| **SSH Port** | 2222 |
| **Jenkins Org** | `jenkins-projects` |
| **GitHub Actions Org** | `github-projects` |
| **Vault Path** | `secret/data/gitea` |

```bash
# Test: curl -H "Authorization: token ${GITEA_TOKEN}" https://gitea.deepaksharma.live/api/v1/user
```

---

## 4. Jenkins

| Field | Value |
|-------|-------|
| **URL** | https://jenkins.deepaksharma.live/jenkins |
| **Username** | `admin` |
| **Password** | `admin123` |
| **API Base** | `https://jenkins.deepaksharma.live/jenkins/api/json` |
| **Agents** | `jenkins-agent-1`, `jenkins-agent-2`, `jenkins-agent-3` |
| **Agent Label** | `docker` |
| **Vault Path** | `secret/data/jenkins` |

```bash
# Test: curl -u admin:admin123 https://jenkins.deepaksharma.live/jenkins/api/json?tree=jobs[name]
```

---

## 5. SonarQube

| Field | Value |
|-------|-------|
| **URL** | https://sonarqube.deepaksharma.live |
| **Username** | `admin` |
| **Password** | `${SONARQUBE_ADMIN_PASSWORD}` |
| **API Token** | `${SONARQUBE_TOKEN}` |
| **Version** | 26.1.0 |
| **Vault Path** | `secret/data/sonarqube` |

```bash
# Test: curl -u "admin:N7@qL9\!fR2#XwA8\$" https://sonarqube.deepaksharma.live/api/system/status
# API: curl -H "Authorization: Bearer ${SONARQUBE_TOKEN}" https://sonarqube.deepaksharma.live/api/projects/search
```

---

## 6. Nexus Repository

| Field | Value |
|-------|-------|
| **UI** | https://nexus.deepaksharma.live |
| **Username** | `admin` |
| **Password** | `Hiagb@1234` |
| **Docker Registry** | `nexus-docker.deepaksharma.live` (host) / `ai-nexus:5001` (containers) |
| **Vault Path** | `secret/data/nexus` |

```bash
# Test: curl -u admin:Hiagb@1234 https://nexus.deepaksharma.live/service/rest/v1/repositories
# Docker login: docker login nexus-docker.deepaksharma.live -u admin -p Hiagb@1234
```

---

## 7. Splunk

| Field | Value |
|-------|-------|
| **URL** | https://splunk.deepaksharma.live/splunk |
| **Username** | `admin` |
| **Password** | `${SPLUNK_PASSWORD}` |
| **REST API** | `https://splunk.deepaksharma.live/splunk/en-US/splunkd/__raw/services` |
| **HEC Port** | 8088 |
| **Vault Path** | `secret/data/splunk` |

```bash
# Test login: curl -X POST https://splunk.deepaksharma.live/splunk/en-US/splunkd/__raw/services/auth/login -d "username=admin&password=Admin%401234&output_mode=json"
```

---

## 8. Grafana

| Field | Value |
|-------|-------|
| **URL** | https://grafana.deepaksharma.live |
| **Username** | `admin` |
| **Password** | `admin123` |
| **Vault Path** | `secret/data/grafana` |

```bash
# Test: curl -u admin:admin123 https://grafana.deepaksharma.live/api/org
```

---

## 9. MinIO

| Field | Value |
|-------|-------|
| **UI** | https://minio.deepaksharma.live |
| **API** | Docker Desktop/container network only |
| **Access Key** | `admin` |
| **Secret Key** | `admin123` |
| **Vault Path** | `secret/data/minio` |

```bash
# Test: curl https://minio.deepaksharma.live/minio/health/live
# Public MinIO console: https://minio.deepaksharma.live/
```

---

## 10. Jira

| Field | Value |
|-------|-------|
| **URL** | https://jira.deepaksharma.live |
| **Username** | `deepak16686` |
| **Password** | `admin123` |
| **Email** | `deepakdce2009@gmail.com` |
| **Groups** | `jira-administrators`, `jira-software-users` |
| **DB** | `jira-postgres` — `jira/jira123@jiradb` |
| **Vault Path** | `secret/data/jira` |
| **Note** | Jira 9+ disables HTTP Basic Auth for REST API by default. UI login works fine. For REST API: generate a PAT at https://jira.deepaksharma.live/secure/ViewProfile.jspa → Personal Access Tokens → Create Token |

---

## 11. Redmine

| Field | Value |
|-------|-------|
| **URL** | https://redmine.deepaksharma.live |
| **Username** | `admin` |
| **Password** | `${SPLUNK_PASSWORD}` |
| **API Key** | `701b636febd66b8335cc485b671c27984d31a10b` |
| **Vault Path** | `secret/data/redmine` |

```bash
# Test: curl -H "X-Redmine-API-Key: 701b636febd66b8335cc485b671c27984d31a10b" https://redmine.deepaksharma.live/users/current.json
```

---

## 12. PostgreSQL (Main)

| Field | Value |
|-------|-------|
| **Host** | `Docker Desktop/container network only` |
| **Username** | `platform` |
| **Password** | `platform123` |
| **Database** | `modernization_platform` |
| **Connection String** | `postgresql://platform:platform123@ai-postgres:5432/modernization_platform (container network)` |
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
| **Redis** | `Docker Desktop/container network only` | No password configured |
| **Prometheus** | https://prometheus.deepaksharma.live/prometheus/ | No auth — health: `/prometheus/-/healthy`, API: `/prometheus/api/v1/` |
| **Jaeger** | https://jaeger.deepaksharma.live | No auth |
| **ChromaDB** | https://chromadb.deepaksharma.live | No auth — use `/api/v2/` (v1 deprecated) |
| **Qdrant** | https://qdrant.deepaksharma.live | No auth |
| **MailHog** | https://mailhog.deepaksharma.live | No auth — SMTP on port 1025 (internal) |

---

## Taskflow Microservices

| Service | URL | Health |
|---------|-----|--------|
| **API Gateway** | https://taskflow.deepaksharma.live/health | `/health` |
| **Auth Service** | https://taskflow-auth.deepaksharma.live/health | `/health` |
| **Task Service** | https://taskflow-task.deepaksharma.live/docs | `/health` |
| **Notification Service** | https://taskflow-notify.deepaksharma.live/health | `/health` |

---

## Observability Stack

| Service | URL | Notes |
|---------|-----|-------|
| **Grafana** | https://grafana.deepaksharma.live | admin/admin123 |
| **Prometheus** | https://prometheus.deepaksharma.live | No auth |
| **Loki** | https://loki.deepaksharma.live | No auth (internal) |
| **Jaeger** | https://jaeger.deepaksharma.live | No auth |
| **cAdvisor** | https://cadvisor.deepaksharma.live | No auth |
| **Node Exporter** | https://node-exporter.deepaksharma.live | No auth |
| **DCGM Exporter** | https://dcgm-exporter.deepaksharma.live | No auth |

---

## AI / ML Services

| Service | URL | Notes |
|---------|-----|-------|
| **Ollama** | https://ollama.deepaksharma.live | No auth |
| **ChromaDB** | https://chromadb.deepaksharma.live | No auth, use `/api/v2/` |
| **Qdrant** | https://qdrant.deepaksharma.live | No auth |
| **ChromaDB Admin** | https://chromadb-admin.deepaksharma.live | No auth (ARM image — may restart) |

---

## Vault Quick Reference

```bash
# Get root token
VAULT_TOKEN=$(docker exec vault sh -c "cat /vault/file/.root-token")

# Read any secret
# Vault secret reads are Docker Desktop/container-only; no shared HTTP URL is published.

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
