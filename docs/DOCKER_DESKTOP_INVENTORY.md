# Docker Desktop — Full Tool Inventory

**Snapshot date:** 2026-04-21
**Docker context:** `desktop-linux`
**Total containers:** 77 (73 running, 4 exited/created)

---

## Core DevOps stack (34 portal tools)

### AI & LLM (4)
| Name | Image | Port | Status |
|---|---|---|---|
| ollama | `ollama/ollama:latest` | 11434 | Up 16h |
| chromadb | `chromadb/chroma:latest` | 8005→8000 | Up 16h |
| chromadb-admin | `fengzhichao/chromadb-admin:latest` | 3001 | Up 9h |
| qdrant | `qdrant/qdrant:v1.12.5` | 6333-6334 | Up 16h (healthy) |

### CI/CD (3)
| Name | Image | Port | Status |
|---|---|---|---|
| jenkins-master | `jenkins/jenkins:lts` | 8080, 50000 | Up 2h (healthy) |
| jenkins-agent-1 / -2 / -3 | `jenkins/inbound-agent:latest` | — | Up 16h |
| gitlab-runner | `gitlab/gitlab-runner:latest` | — | Up 16h |
| gitea-runner | `localhost:5001/apm-repo/demo/gitea-act-runner:latest` | — | Up 16h |

### SCM (2)
| Name | Image | Port | Status |
|---|---|---|---|
| gitlab-server | `gitlab/gitlab-ce:latest` | 8929→80, 2224→22 | Up 16h (healthy) |
| gitea-server | `gitea/gitea:latest` | 3002→3000, 2222→22 | Up 2h (healthy) |

### Code Quality (1)
| Name | Image | Port | Status |
|---|---|---|---|
| ai-sonarqube | `sonarqube:latest` | 9002→9000 | Up 2h (healthy) |
| ai-sonar-db | `postgres:15-alpine` | internal 5432 | Up 16h (healthy) |

### Security (2)
| Name | Image | Port | Status |
|---|---|---|---|
| vault | `hashicorp/vault:1.15` | 8200 | Up 16h (healthy) |
| vault-unseal | `hashicorp/vault:1.15` | internal 8200 | Up 16h |
| trivy-server | `aquasec/trivy:latest` | 8183→8080 | Up 16h |

### Registry (2)
| Name | Image | Port | Status |
|---|---|---|---|
| ai-nexus | `sonatype/nexus3:latest` | 8181→8081, 5001 (Docker registry) | Up 4m |

### Observability (5)
| Name | Image | Port | Status |
|---|---|---|---|
| grafana | `grafana/grafana:latest` | 3000 | Up 8h |
| prometheus | (image sha `1f0f50f06aca`) | 9090 | Up 16h |
| loki | `grafana/loki:latest` | 3100 | Up 16h |
| jaeger | `jaegertracing/all-in-one:latest` | 16686, 14268 | Up 16h (healthy) |
| promtail | `grafana/promtail:latest` | — | Up 16h |

### Metrics & Exporters (3)
| Name | Image | Port | Status |
|---|---|---|---|
| cadvisor | `gcr.io/cadvisor/cadvisor:latest` | 8182→8080 | Up 16h (healthy) |
| node-exporter | `prom/node-exporter:latest` | 9100 | Up 16h (healthy) |
| dcgm-exporter | `nvidia/dcgm-exporter:3.3.8-3.6.0-ubuntu22.04` | 9400 | Up 16h |

### Logging (1)
| Name | Image | Port | Status |
|---|---|---|---|
| ai-splunk | `splunk/splunk:latest` | 10000→8000, 8088 | Up 16h (healthy) |

### Databases & Storage (3)
| Name | Image | Port | Status |
|---|---|---|---|
| ai-postgres | `postgres:15-alpine` | 5432 | Up 16h (healthy) |
| redis | (image sha `ee64a64eaab6`) | 6379 | Up 16h (healthy) |
| minio | `minio/minio` | 9000-9001 | Up 3h |

### Project Management (2)
| Name | Image | Port | Status |
|---|---|---|---|
| jira | `atlassian/jira-software:9.12` | 8180→8080 | Up 2h |
| jira-postgres | `postgres:15` | internal 5432 | Up 16h (healthy) |
| redmine | `redmine:5-alpine` | 8090→3000 | Up 2h (healthy) |
| redmine-db | `postgres:15-alpine` | internal 5432 | Up 16h (healthy) |

### Gateway & Proxy (1)
| Name | Image | Port | Status |
|---|---|---|---|
| nginx-proxy | `nginx:1.27-alpine` | 8443 (HTTPS SNI), 8070 (HTTP path-router) | Up 7h |

### Platform API (2)
| Name | Image | Port | Status |
|---|---|---|---|
| devops-tools-backend | `devops-tools-backend:latest` | 8003 | Up 57m (healthy) |
| (frontend served by backend) | — | 8003/ | — |

---

## Brandmatik project stack (13 services)

| Name | Image | Port |
|---|---|---|
| brandmatik-api-gateway | brandmatik/brandmatik-api-gateway:latest | 8100→8000 |
| brandmatik-trend-collector | brandmatik/brandmatik-trend-collector:latest | 8101→8001 |
| brandmatik-scoring-engine | brandmatik/brandmatik-scoring-engine:latest | 8102→8002 |
| brandmatik-content-generator | brandmatik/brandmatik-content-generator:latest | 8103→8003 |
| brandmatik-business-service | brandmatik/brandmatik-business-service:latest | 8104→8004 |
| brandmatik-posting-service | brandmatik/brandmatik-posting-service:latest | 8105→8005 |
| brandmatik-analytics-service | brandmatik/brandmatik-analytics-service:latest | 8106→8006 |
| brandmatik-feedback-service | brandmatik/brandmatik-feedback-service:latest | 8107→8007 |
| brandmatik-notification-service | brandmatik/brandmatik-notification-service:latest | 8108→8008 |
| brandmatik-mock-social-poster | brandmatik/brandmatik-mock-social-poster:latest | 8110→8010 |
| brandmatik-postgres | postgres:16-alpine | 5433→5432 |
| brandmatik-redis | redis:7.4-alpine | 6380→6379 |
| brandmatik-qdrant | qdrant/qdrant:v1.12.5 | 6335→6333 |

---

## Chaos Platform stack (15 services)

| Name | Image | Port |
|---|---|---|
| chaos-api-gateway | chaos-platform-setup-api-gateway | 28080→8080 |
| chaos-auth-service | chaos-platform-setup-auth-service | 28081→8081 |
| chaos-experiment-engine | chaos-platform-setup-experiment-engine | 28082→8082 |
| chaos-telemetry-aggregator | chaos-platform-setup-telemetry-aggregator | 28083, 50051 |
| chaos-ai-engine | chaos-platform-setup-ai-engine | 28084→8084 |
| chaos-report-service | chaos-platform-setup-report-service | 28085→8085 |
| chaos-notification-service | chaos-platform-setup-notification-service | 28086→8086 |
| chaos-target-app-1 / -2 / -3 | chaos-platform-setup-target-app-* | 28090-28092 |
| chaos-credentials-dashboard | chaos-platform-setup-credentials-dashboard | 9091 |
| chaos-portal-ui | chaos-platform-setup-portal-ui | 13001→3001 |
| chaos-grafana | grafana/grafana:latest | 13000→3000 |
| chaos-prometheus | prom/prometheus:latest | 19090→9090 |
| chaos-minio | minio/minio:latest | 19000-19001→9000-9001 |
| chaos-nats | nats:2.10-alpine | 4222, 8222 |
| chaos-postgres | postgres:16-alpine | 15432→5432 |
| chaos-redis | redis:7-alpine | 16379→6379 |
| chaos-agent-sim | chaos-platform-setup-chaos-agent | Exited 10d ago |

---

## Taskflow project stack (5 services)

| Name | Image | Port |
|---|---|---|
| taskflow-api-gateway | taskflow-api-gateway | 18080→8080 |
| taskflow-auth-service | taskflow-auth-service | 18081→8080 |
| taskflow-task-service | taskflow-task-service | 18082→8080 |
| taskflow-notification-service | taskflow-notification-service | 18083→8080 |
| taskflow-mailhog | mailhog/mailhog:latest | 8025 |

---

## Misc / init containers

| Name | Image | Status |
|---|---|---|
| rbac-init | hashicorp/vault:1.15 | Created (one-shot) |
| vault-init | hashicorp/vault:1.15 | Exited 5w ago (one-shot) |
| brandmatik-db-migrations | brandmatik/brandmatik-db-migrations:latest | Exited 10d ago (one-shot) |
| chatbot-portal | dev-stack-chatbot-portal | Removed; legacy UI is profile-gated and replaced by devops-tools-backend on 8003 |

---

## Host port allocation (what's reachable from Windows)

Unique host ports bound to loopback (127.0.0.1:...) or 0.0.0.0:... across all containers:

```
2222  → gitea SSH
2224  → gitlab SSH
3000  → grafana
3001  → chromadb-admin
3002  → gitea web
3005  → unbound (legacy chatbot-portal removed)
3100  → loki
4222  → chaos-nats (client)
5001  → ai-nexus Docker registry
5432  → ai-postgres
5433  → brandmatik-postgres
6333  → qdrant
6334  → qdrant
6335  → brandmatik-qdrant
6336  → brandmatik-qdrant
6379  → redis
6380  → brandmatik-redis
8003  → devops-tools-backend (portal)
8025  → taskflow-mailhog
8070  → nginx-proxy path-router (Tailscale funnel target)
8080  → jenkins-master
8088  → ai-splunk HEC
8090  → redmine
8100  → brandmatik-api-gateway
8101-8110 → brandmatik-* services
8180  → jira
8181  → ai-nexus UI
8182  → cadvisor
8183  → trivy-server
8200  → vault
8222  → chaos-nats (monitoring)
8443  → nginx-proxy SNI (localhost only)
8929  → gitlab web
9000-9001 → minio (S3 + console)
9002  → ai-sonarqube
9090  → prometheus
9100  → node-exporter
9400  → dcgm-exporter
9091  → chaos-credentials-dashboard
10000 → ai-splunk web
11434 → ollama
13000 → chaos-grafana
13001 → chaos-portal-ui
14268 → jaeger collector
15432 → chaos-postgres
16379 → chaos-redis
16686 → jaeger UI
18080-18083 → taskflow-*
19000-19001 → chaos-minio
19090 → chaos-prometheus
28080-28092 → chaos-*
50000 → jenkins agent bootstrap
50051 → chaos-telemetry (gRPC)
```

---

## Source of truth

Portal tool registry: `devops-tools-backend/config/tools.yaml` (34 entries; this inventory is a superset covering project stacks too).

Regenerate with:
```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | sort
```
