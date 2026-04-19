# Docker Desktop Read-Only Inventory

**Host**: Windows 11 + WSL2 + Docker Desktop  
**Captured**: 2026-04-19 at ~16:30-16:45 IST (context: `desktop-linux`)  
**Scope**: Docker engine + Docker Desktop Kubernetes  
**Mode**: Read-only discovery. No containers/volumes/networks/images were modified, removed, or restarted.

---

## 1. Engine / Contexts / Plugins

| Property | Value | Source |
| --- | --- | --- |
| Server Version | **29.4.0** | `docker info` |
| OS Type | linux (Docker Desktop, Linux engine via WSL2) | `docker info` |
| Architecture | x86_64 | `docker info` |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 | `docker info` |
| Allocated CPUs | 48 | `docker info` |
| Allocated Memory | 134,712,389,632 bytes (**~125 GiB**) | `docker info` |
| Storage Driver | overlayfs | `docker info` |
| Default Runtime | runc | `docker info` |
| Runtimes registered | `runc`, `io.containerd.runc.v2`, **`nvidia`** (nvidia-container-runtime) | `docker info` |
| Containers (total) | 80 | `docker info` |
| Containers running | 76 | `docker info` |
| Containers stopped | 4 (3 exited + 1 created) | `docker info` |
| Images | 1,040 | `docker info` |
| Docker Root Dir | `/var/lib/docker` (inside Docker Desktop VM) | `docker info` |
| Compose version | **v5.1.1** | `docker compose version` |
| Buildx version | **v0.33.0-desktop.1** (commit 7f91f038) | `docker buildx version` |
| Plugins | **none installed** | `docker plugin ls` (empty table) |

### Docker contexts

```
$ docker context ls
NAME              DESCRIPTION                               DOCKER ENDPOINT
default           Current DOCKER_HOST based configuration   npipe:////./pipe/docker_engine
desktop-linux *   Docker Desktop                            npipe:////./pipe/dockerDesktopLinuxEngine
```

> **Env-fix reminder**: shell-level `DOCKER_HOST=unix:///var/run/docker.sock` is present in user's Git Bash profile and points at a non-existent WSL socket. Every docker/compose call in this report was preceded by `unset DOCKER_HOST && export DOCKER_CONTEXT=desktop-linux`.

### NVIDIA runtime

`nvidia` runtime is registered at the engine. Docker Desktop Kubernetes does NOT forward GPUs to pods; GPU workloads must run as containers via `docker run --gpus all` or Compose `deploy.resources.reservations.devices`. Ollama is the only running container that would benefit (see Tool Matrix; GPU-access validity not verified in this read-only pass).

---

## 2. Compose files discovered

Searched under `C:\Users\deepak\ai-folder` (depth ≤ 5, excluding node_modules) plus the two known external project roots the engine shows as active config files.

| Path | Project (claimed) | Running/Registered | Services (parsed from file) | Named volumes | Networks |
| --- | --- | --- | --- | --- | --- |
| `C:\Users\deepak\ai-folder\desktop-content\files\docker-compose.yml` | — | not registered | _not parsed (not active)_ | _not parsed_ | _not parsed_ |
| `C:\Users\deepak\ai-folder\devops-tools-backend\docker-compose.yml` | `devops-tools-backend` (historical) | **not active** — historical project, volumes retained | _not parsed_ (superseded by dev-stack) | _not parsed_ | _not parsed_ |
| `C:\Users\deepak\ai-folder\files\docker-compose.yml` | — | not registered | _not parsed_ | _not parsed_ | _not parsed_ |
| `C:\Users\deepak\ai-folder\legacy-modernization-api\docker-compose.yml` | — | not registered | _not parsed_ | _not parsed_ | _not parsed_ |
| `C:\Users\deepak\ai-folder\plane\docker-compose.yml` | `plane` | **not active** — volumes retained | _not parsed_ (same name collision with redmine plugin) | `redmine-data`, `redmine-db-data`, `redmine-plugins`, `redmine-themes` (retained) | _not parsed_ |
| `C:\Users\deepak\ai-folder\platform-setup\docker-compose.yml` | — | not registered | _not parsed_ | _not parsed_ | _not parsed_ |
| `D:\Repos\ai-folder\infra-stack\docker-compose.yml` (+ include shards `ai.yml`, `cicd.yml`, `core.yml`, `monitoring.yml`, `projects.yml`, `quality.yml`, `scm.yml`) | **`infra-stack`** | running (35) + 1 exited + 1 created | See per-shard breakdown below | See running networks + volumes per shard below | `global-infra-net`, `ai-platform-net`, `gitlab-net`, `monitoring-network`, `ticketing-net`, `jenkins-net` |
| `D:\Repos\ai-folder\dev-stack\infrastructure\docker-compose.yml` | **`dev-stack`** | running (2) | `devops-tools-backend`, `chatbot-portal` | `devops-tools-config`, `vault-data` | `global-infra-net` (external) |
| `D:\Repos\Mkt-solution\docker-compose.yml` | **`brandmatik`** | running (13) + 1 exited | `postgres`, `redis`, `qdrant`, `db-migrations`, `api-gateway`, `trend-collector`, `scoring-engine`, `content-generator`, `business-service`, `posting-service`, `analytics-service`, `feedback-service`, `notification-service`, `mock-social-poster`, `prometheus`, `grafana` | `brandmatik-pgdata`, `brandmatik-redis`, `brandmatik-qdrant`, `brandmatik-prometheus`, `brandmatik-grafana` | `brandmatik-net` |
| `C:\Users\deepak\chaos-platform-setup\docker-compose.yml` | **`chaos-platform-setup`** | running (18) + 1 exited | `postgres`, `redis`, `nats`, `minio`, `api-gateway`, `auth-service`, `experiment-engine`, `telemetry-aggregator`, `ai-engine`, `report-service`, `notification-service`, `portal-ui`, `chaos-agent`, `prometheus`, `grafana`, `credentials-dashboard`, `target-app-1`, `target-app-2`, `target-app-3` | `postgres_data`, `redis_data`, `minio_data`, `prometheus_data`, `grafana_data` | `chaos_network` |
| `C:\Users\deepak\test-repo\taskflow\docker-compose.yml` | **`taskflow`** | running (5) | `api-gateway`, `auth-service`, `task-service`, `notification-service`, `mailhog` | _(none declared inline; uses image data dirs or host paths)_ | `global-infra-net` (external) |
| `C:\Users\deepak\test-repo\taskflow\docker-compose.dev.yml` | taskflow (override) | not applied as separate project | _overrides of above_ | _none_ | _none new_ |

### infra-stack shard → service map (parsed from `/d/Repos/ai-folder/infra-stack/*.yml`)

| Shard | Services |
| --- | --- |
| `ai.yml` | ollama, chromadb, chromadb-admin, qdrant |
| `cicd.yml` | jenkins-master, jenkins-agent-1, jenkins-agent-2, jenkins-agent-3 |
| `core.yml` | ai-postgres, redis, minio |
| `monitoring.yml` | prometheus, grafana, loki, promtail, jaeger, node-exporter, cadvisor, dcgm-exporter, ai-splunk |
| `projects.yml` | jira, jira-postgres, redmine, redmine-db |
| `quality.yml` | ai-sonarqube, ai-sonar-db, ai-nexus, trivy-server |
| `scm.yml` | gitlab-server, gitlab-runner, gitea-server, gitea-runner |

Root file also adds: `nginx-proxy`, `vault`, `vault-unseal`, `vault-init` (exited), `rbac-init` (created). 35 running containers total.

---

## 3. Compose projects (running)

From `docker compose ls -a`:

| Project | Status | Config File | Running count | Primary purpose |
| --- | --- | --- | --- | --- |
| **infra-stack** | `created(1), exited(1), running(35)` | `D:\Repos\ai-folder\infra-stack\docker-compose.yml` | 35 | Central DevOps tooling: Jenkins x4, GitLab+runner, Gitea+runner, Sonar+DB, Nexus, Vault (+unseal), Jira+DB, Redmine+DB, Prom/Grafana/Loki/Promtail/Jaeger, MinIO, Postgres, Redis, Trivy, Splunk, Ollama, Chroma, Chroma-admin, Qdrant, node-exporter, cadvisor, dcgm-exporter, nginx-proxy |
| **chaos-platform-setup** | `exited(1), running(18)` | `C:\Users\deepak\chaos-platform-setup\docker-compose.yml` | 18 | Chaos engineering platform: api/auth/experiment/ai/report/notification/telemetry services + credentials-dashboard + portal-ui + 3 target apps + own postgres/redis/minio/nats/prom/grafana |
| **brandmatik** | `exited(1), running(13)` | `D:\Repos\Mkt-solution\docker-compose.yml` | 13 | Marketing-automation microservices: api-gateway + 10 app services + postgres/redis/qdrant (db-migrations exited 0 after seed) |
| **taskflow** | `running(5)` | `C:\Users\deepak\test-repo\taskflow\docker-compose.yml` | 5 | Task-management demo: api-gateway + 3 services + mailhog (joins `global-infra-net` to reuse infra postgres/redis) |
| **dev-stack** | `running(2)` | `D:\Repos\ai-folder\dev-stack\infrastructure\docker-compose.yml` | 2 | `devops-tools-backend` (FastAPI 8003) + `chatbot-portal` (Nginx UI on 3005→3001) |

---

## 4. Compose projects (stopped or partial)

No fully-stopped compose projects are registered with the engine. The four non-running containers are individual services inside running projects:

| Container | Project | State | Why |
| --- | --- | --- | --- |
| `vault-init` | infra-stack | Exited (0) 5 weeks ago | One-shot init job. Completed successfully. |
| `brandmatik-db-migrations` | brandmatik | Exited (0) 9 days ago | One-shot `alembic upgrade head`. Completed. |
| `chaos-agent-sim` | chaos-platform-setup | Exited (0) 9 days ago | Short-lived simulator. |
| `rbac-init` | infra-stack | Created (never started) | `/bin/sh /rbac-init.sh …` — init job never triggered. Unknown — not started since last compose up. |

### Historical projects whose *volumes still exist* but whose *containers are gone*

These have no running/stopped containers but their named volumes are retained (see §6 for full list):

- `ai-folder` (old compose project — has `grafana-data`, `loki-data`, `prometheus-data`)
- `ai-lab` (14 volumes: dind/gitlab x5/grafana/loki/ollama/prometheus/qdrant)
- `backend` (1 volume)
- `brandmatik-infra` (4 volumes: gitlab x3 + nexus)
- `clawd` (6 volumes: jenkins master + 3 agents + 2 workspaces)
- `devops-tools-backend` (3 volumes including `jira_data` 972.5M, `jira_postgres_data` 84.9M — DUPLICATES of live infra-stack data)
- `gitea-setup` (2 volumes — DUPLICATE of infra-stack gitea)
- `infrastructure` (1 volume: `vault-data`)
- `mkt-solution` (6 volumes — likely ancestor of `brandmatik`)
- `mkt-stack` (8 volumes)
- `plane` (4 redmine volumes — DUPLICATE of infra-stack redmine)
- `prod-stack` (27 "prod-*" volumes — cold replica set)

---

## 5. Containers (all 80 — grouped by compose project)

Captured via `docker ps -a --format '{{.Names}}||{{.Image}}||{{.State}}||{{.Status}}||{{.Ports}}||{{.Label "com.docker.compose.project"}}||{{.Label "com.docker.compose.service"}}'`.

### infra-stack (35 running + 1 exited + 1 created = 37 total)

| Container | Image | State | Status | Host → container ports |
| --- | --- | --- | --- | --- |
| ai-nexus | sonatype/nexus3:latest | running | Up 46m | 5001→5001/tcp, 8181→8081/tcp |
| ai-postgres | postgres:15-alpine | running | Up 46m (healthy) | 5432→5432/tcp |
| ai-sonar-db | postgres:15-alpine | running | Up 46m (healthy) | internal 5432 only |
| ai-sonarqube | sonarqube:latest | running | Up 46m (healthy) | 9002→9000/tcp |
| ai-splunk | splunk/splunk:latest | running | Up 46m (healthy) | 8088→8088, 10000→8000 |
| cadvisor | gcr.io/cadvisor/cadvisor:latest | running | Up 46m (healthy) | 8182→8080 |
| chromadb | chromadb/chroma:latest | running | Up 46m | 8005→8000 |
| chromadb-admin | sanderdw/chromadb-admin:latest | running | Up 46m | 3001→3000 |
| dcgm-exporter | nvidia/dcgm-exporter:3.3.8-3.6.0-ubuntu22.04 | running | Up 46m | 9400→9400 |
| gitea-runner | localhost:5001/apm-repo/demo/gitea-act-runner:latest | running | Up 45m | _none_ |
| gitea-server | gitea/gitea:latest | running | Up 46m (healthy) | 2222→22 (SSH), 3002→3000 |
| gitlab-runner | gitlab/gitlab-runner:latest | running | Up 46m | _none_ |
| gitlab-server | gitlab/gitlab-ce:latest | running | Up 46m (healthy) | 2224→22 (SSH), 8929→80 |
| grafana | image-ID 9e1e77ade304 | running | Up 46m (healthy) | 3000→3000 |
| jaeger | jaegertracing/all-in-one:latest | running | Up 46m (healthy) | 14268→14268, 16686→16686 |
| jenkins-agent-1 | jenkins/inbound-agent:latest | running | Up 46m | _none_ |
| jenkins-agent-2 | jenkins/inbound-agent:latest | running | Up 46m | _none_ |
| jenkins-agent-3 | jenkins/inbound-agent:latest | running | Up 46m | _none_ |
| jenkins-master | jenkins/jenkins:lts | running | Up 46m (healthy) | 8080→8080, 50000→50000 |
| jira | atlassian/jira-software:9.12 | running | Up 46m | 8180→8080 |
| jira-postgres | postgres:15 | running | Up 46m (healthy) | internal 5432 only |
| loki | grafana/loki:latest | running | Up 46m | 3100→3100 |
| minio | minio/minio | running | Up 46m (healthy) | 9000-9001→9000-9001 |
| nginx-proxy | nginx:alpine | running | Up 46m (healthy) | 8443→80 |
| node-exporter | prom/node-exporter:latest | running | Up 46m (healthy) | 9100→9100 |
| ollama | ollama/ollama:latest | running | Up 46m | 11434→11434 |
| prometheus | image-ID 1f0f50f06aca | running | Up 46m | 9090→9090 |
| promtail | grafana/promtail:latest | running | Up 46m | _none_ |
| qdrant | qdrant/qdrant:v1.12.5 | running | Up 46m (healthy) | 6333-6334→6333-6334 |
| rbac-init | hashicorp/vault:1.15 | **created** | Created (never started) | _none_ |
| redis | image-ID ee64a64eaab6 | running | Up 46m (healthy) | 6379→6379 |
| redmine | redmine:5-alpine | running | Up 46m (healthy) | 8090→3000 |
| redmine-db | postgres:15-alpine | running | Up 46m (healthy) | internal 5432 only |
| trivy-server | aquasec/trivy:latest | running | Up 46m | 8183→8080 |
| vault | hashicorp/vault:1.15 | running | Up 46m (healthy) | 8200→8200 |
| vault-init | hashicorp/vault:1.15 | **exited(0) 5 weeks ago** | _one-shot init_ | _none_ |
| vault-unseal | hashicorp/vault:1.15 | running | Up 46m | internal 8200 |

### dev-stack (2 running)

| Container | Image | State | Status | Host → container ports |
| --- | --- | --- | --- | --- |
| devops-tools-backend | dev-stack-devops-tools-backend (local build) | running | Up 46m (healthy) | 8003→8003 |
| chatbot-portal | dev-stack-chatbot-portal (local nginx build) | running | **Up 46m (UNHEALTHY)** | 3005→3001 |

### brandmatik (13 running + 1 exited)

| Container | Image | State | Status | Host → container ports |
| --- | --- | --- | --- | --- |
| brandmatik-analytics-service | localhost:8082/brandmatik/brandmatik-analytics-service:latest | running | Up 46m (healthy) | 8106→8006 |
| brandmatik-api-gateway | localhost:8082/brandmatik/brandmatik-api-gateway:latest | running | Up 46m (healthy) | 8100→8000 |
| brandmatik-business-service | localhost:8082/brandmatik/brandmatik-business-service:latest | running | Up 46m (healthy) | 8104→8004 |
| brandmatik-content-generator | localhost:8082/brandmatik/brandmatik-content-generator:latest | running | Up 46m (healthy) | 8103→8003 |
| brandmatik-db-migrations | localhost:8082/brandmatik/brandmatik-db-migrations:latest | **exited(0) 9d ago** | _alembic upgrade head_ | _none_ |
| brandmatik-feedback-service | localhost:8082/brandmatik/brandmatik-feedback-service:latest | running | Up 46m (healthy) | 8107→8007 |
| brandmatik-mock-social-poster | localhost:8082/brandmatik/brandmatik-mock-social-poster:latest | running | Up 46m (healthy) | 8110→8010 |
| brandmatik-notification-service | localhost:8082/brandmatik/brandmatik-notification-service:latest | running | Up 46m (healthy) | 8108→8008 |
| brandmatik-postgres | postgres:16-alpine | running | Up 46m (healthy) | 5433→5432 |
| brandmatik-posting-service | localhost:8082/brandmatik/brandmatik-posting-service:latest | running | Up 46m (healthy) | 8105→8005 |
| brandmatik-qdrant | qdrant/qdrant:v1.12.5 | running | Up 46m (healthy) | 6335→6333, 6336→6334 |
| brandmatik-redis | redis:7.4-alpine | running | Up 46m (healthy) | 6380→6379 |
| brandmatik-scoring-engine | localhost:8082/brandmatik/brandmatik-scoring-engine:latest | running | Up 46m (healthy) | 8102→8002 |
| brandmatik-trend-collector | localhost:8082/brandmatik/brandmatik-trend-collector:latest | running | Up 46m (healthy) | 8101→8001 |

> **Note**: Image registry `localhost:8082` is the brandmatik-infra Nexus (NOT the infra-stack `ai-nexus` which is on 8181). The brandmatik-infra stack itself is not running, but its images were cached and the live Nexus (`ai-nexus` 8181) does not have a `brandmatik` repo. After a prune these tags may become un-repullable.

### chaos-platform-setup (18 running + 1 exited)

| Container | Image | State | Status | Host → container ports |
| --- | --- | --- | --- | --- |
| chaos-agent-sim | chaos-platform-setup-chaos-agent | **exited(0) 9d ago** | one-shot | _none_ |
| chaos-ai-engine | chaos-platform-setup-ai-engine | running | Up 46m (healthy) | 28084→8084 |
| chaos-api-gateway | chaos-platform-setup-api-gateway | running | Up 46m (healthy) | 28080→8080 |
| chaos-auth-service | chaos-platform-setup-auth-service | running | Up 46m (healthy) | 28081→8081 |
| chaos-credentials-dashboard | chaos-platform-setup-credentials-dashboard | running | Up 46m (healthy) | 9091→9091 |
| chaos-experiment-engine | chaos-platform-setup-experiment-engine | running | Up 46m (healthy) | 28082→8082 |
| chaos-grafana | grafana/grafana:latest | running | Up 46m (healthy) | 13000→3000 |
| chaos-minio | minio/minio:latest | running | Up 46m (healthy) | 19000→9000, 19001→9001 |
| chaos-nats | nats:2.10-alpine | running | Up 46m (healthy) | 4222→4222, 8222→8222 |
| chaos-notification-service | chaos-platform-setup-notification-service | running | Up 45m (healthy) | 28086→8086 |
| chaos-portal-ui | chaos-platform-setup-portal-ui | running | Up 46m (healthy) | 13001→3001 |
| chaos-postgres | postgres:16-alpine | running | Up 46m (healthy) | 15432→5432 |
| chaos-prometheus | prom/prometheus:latest | running | Up 46m (healthy) | 19090→9090 |
| chaos-redis | redis:7-alpine | running | Up 46m (healthy) | 16379→6379 |
| chaos-report-service | chaos-platform-setup-report-service | running | Up 46m (healthy) | 28085→8085 |
| chaos-target-app-1 | chaos-platform-setup-target-app-1 | running | Up 46m (healthy) | 28090→8090 |
| chaos-target-app-2 | chaos-platform-setup-target-app-2 | running | Up 46m (healthy) | 28091→8090 |
| chaos-target-app-3 | chaos-platform-setup-target-app-3 | running | Up 46m (healthy) | 28092→8090 |
| chaos-telemetry-aggregator | chaos-platform-setup-telemetry-aggregator | running | Up 45m (healthy) | 50051→50051 (gRPC), 28083→8083 |

### taskflow (5 running)

| Container | Image | State | Status | Host → container ports |
| --- | --- | --- | --- | --- |
| taskflow-api-gateway | taskflow-api-gateway | running | Up 46m (healthy) | 18080→8080 |
| taskflow-auth-service | taskflow-auth-service | running | Up 46m (healthy) | 18081→8080 |
| taskflow-mailhog | mailhog/mailhog:latest | running | Up 46m | 8025→8025 (MailHog web + SMTP on same) |
| taskflow-notification-service | taskflow-notification-service | running | Up 46m (healthy) | 18083→8080 |
| taskflow-task-service | taskflow-task-service | running | Up 46m (healthy) | 18082→8080 |

**Grand total**: 35 + 18 + 13 + 5 + 2 + (3 exited one-shots + 1 created) = **77 containers with compose labels**. `docker info` reports 80 total — gap of 3 is explained by K8s control-plane containers (`desktop-control-plane`, `kind-cloud-provider`, `kind-registry-mirror`) which have no compose labels (see §7).

---

## 6. Named volumes

Engine has **808 total volumes**: **187 named** + **621 anonymous** (64-hex IDs, one per container discard). Of the 187 named, **500 are `runner-*` GitLab CI cache volumes** (noise — each CI job creates two: `cache-<sha>` and `cache-<sha>-protected`), and the rest are genuine stack-owned volumes.

> **Sizes measured** with `docker run --rm -v <vol>:/vol alpine:3.20 du -sh /vol` (one-shot throw-away probe, no mutation). Only the volumes relevant to active/retained stacks were sized; runner-* caches are not listed individually.

### Volumes in use by RUNNING containers (critical — DO NOT TOUCH)

| Volume | Size | Mounted by | Compose project | Has data? |
| --- | --- | --- | --- | --- |
| `ai-folder_grafana-data` | 145.6 MB | grafana | *legacy `ai-folder` project* (still mounted by infra-stack grafana) | yes |
| `ai-folder_loki-data` | 395.2 MB | loki | *legacy `ai-folder` project* (still mounted by infra-stack loki) | yes |
| `ai-folder_prometheus-data` | 1.3 GB | prometheus | *legacy `ai-folder` project* (still mounted by infra-stack prometheus) | yes |
| `brandmatik_brandmatik-pgdata` | 77.4 MB | brandmatik-postgres | brandmatik | yes |
| `brandmatik_brandmatik-qdrant` | 20 KB | brandmatik-qdrant | brandmatik | **empty** (fresh) |
| `brandmatik_brandmatik-redis` | 2.4 MB | brandmatik-redis | brandmatik | yes |
| `brandmatik_brandmatik-grafana` | 1.0 MB | _(declared, not currently mounted in running set — verify)_ | brandmatik | minimal |
| `brandmatik_brandmatik-prometheus` | 27.7 MB | _(declared)_ | brandmatik | yes |
| `chaos-platform-setup_grafana_data` | 50.6 MB | chaos-grafana | chaos-platform-setup | yes |
| `chaos-platform-setup_minio_data` | 136 KB | chaos-minio | chaos-platform-setup | minimal |
| `chaos-platform-setup_postgres_data` | 66.4 MB | chaos-postgres | chaos-platform-setup | yes |
| `chaos-platform-setup_prometheus_data` | 70.9 MB | chaos-prometheus | chaos-platform-setup | yes |
| `chaos-platform-setup_redis_data` | 12 KB | chaos-redis | chaos-platform-setup | **empty** |
| `chromadb-data` | 1.1 MB | chromadb | infra-stack (short volume name) | yes (small) |
| `clawd_jenkins-agent-1-data` | _not sized_ | jenkins-agent-1 | *legacy `clawd` project* (still mounted) | unknown |
| `clawd_jenkins-agent-2-data` | _not sized_ | jenkins-agent-2 | *legacy `clawd` project* | unknown |
| `clawd_jenkins-agent-3-data` | _not sized_ | jenkins-agent-3 | *legacy `clawd` project* | unknown |
| `clawd_jenkins-data` | _not sized_ | jenkins-master | *legacy `clawd` project* | unknown |
| `devops-tools-backend_devops-tools-config` | _not sized_ | devops-tools-backend (via `dev-stack`) *or* anonymous for legacy project | ambiguous | unknown |
| `devops-tools-backend_jira_data` | 972.5 MB | **historically brandmatik/devops-tools — now used by infra-stack `jira`** | infra-stack effectively | yes (large) |
| `devops-tools-backend_jira_postgres_data` | 84.9 MB | jira-postgres | infra-stack effectively | yes |
| `gitea-setup_gitea-data` | 56.6 MB | gitea-server | *legacy `gitea-setup` project* (still mounted) | yes |
| `gitea-setup_gitea-runner-data` | 21.1 MB | gitea-runner | *legacy `gitea-setup` project* | yes |
| `minio-data` | 232 KB | minio (infra-stack) | infra-stack | minimal |
| `nexus-data` | **38.2 GB** | ai-nexus | infra-stack | YES — **LARGEST STATEFUL** |
| `ollama` | **23.4 GB** | ollama | infra-stack (short name, unlabelled) | YES — model cache |
| `plane_redmine-data` | 4 KB | redmine | *legacy `plane` project* (still mounted) | empty |
| `plane_redmine-db-data` | 48.9 MB | redmine-db | *legacy `plane` project* | yes |
| `plane_redmine-plugins` | 8 KB | redmine | *legacy `plane` project* | empty |
| `plane_redmine-themes` | 44 KB | redmine | *legacy `plane` project* | small |
| `postgres-data` | 76.6 MB | ai-postgres | infra-stack | yes |
| `qdrant-data` | 20 KB | qdrant | infra-stack (via `dev-stack`-labelled volume, see note) | **empty** |
| `redis-data` | 20 KB | redis | infra-stack | **empty** (Redis is ephemeral) |
| `sonarqube-data` | 327.7 MB | ai-sonarqube | infra-stack | yes |
| `sonarqube-extensions` | 28 KB | ai-sonarqube | infra-stack | minimal |
| `sonarqube-logs` | 1.3 MB | ai-sonarqube | infra-stack | yes |
| `sonarqube-postgres-data` | 132.3 MB | ai-sonar-db | infra-stack | yes |
| `trivy-cache` | 1.0 GB | trivy-server | infra-stack | yes — vuln DB |
| `vault-data` | _(short name, infrastructure project label)_ | vault | infra-stack | unknown — sized below |

Additional "short-name" / unlabelled volumes still in use (also sized):

| Volume | Size | Notes |
| --- | --- | --- |
| `infra-stack_vault-data` | 4.0 KB | **empty** — looks like current infra-stack project version |
| `dev-stack_devops-tools-config` | 4.0 KB | empty |
| `sonar-data` | 147.4 MB | older alias, retained |
| `prod-splunk-etc` | 1.2 GB | cold replica (prod-stack project, not running) |
| `prod-splunk-var` | 1.6 GB | cold replica |
| `maven-repo-cache` | 4.0 KB | empty |

> **Interpretation**: Several "legacy" compose projects are still mounted by running infra-stack containers because the compose files *externally reference* those volumes by name. Specifically, `ai-folder_*`, `devops-tools-backend_jira*`, `gitea-setup_*`, `plane_redmine-*`, `clawd_jenkins-*` volumes are ALL live-mounted by current running containers. **None of these can be pruned**.

### Volumes NOT currently mounted by any running container (candidates — confirm before touching)

Parsed by cross-referencing named-volume list against running-container mount list. These have `RefCount = 0` from a running-container perspective (they may still be referenced by the *exited* brandmatik-db-migrations etc, so treat "RefCount" here as "not mounted by running containers"):

- `act-toolcache`
- `ai-lab_dind_data`, `ai-lab_gitlab_config`, `ai-lab_gitlab_data`, `ai-lab_gitlab_logs`, `ai-lab_gitlab_runner_config`, `ai-lab_grafana_data`, `ai-lab_loki_data`, `ai-lab_ollama_data`, `ai-lab_prometheus_data`, `ai-lab_qdrant_data` (14 vols, legacy ai-lab project)
- `backend_devops-tools-config`
- `brandmatik-infra_gitlab-config`, `brandmatik-infra_gitlab-data`, `brandmatik-infra_gitlab-logs`, `brandmatik-infra_nexus-data` (hosts local Nexus @ 8082 that brandmatik images claim)
- `clawd_jenkins-agent1-workspace`, `clawd_jenkins-agent2-workspace` (2 workspace vols — but `clawd_jenkins-*-data` DO attach to running agents)
- `grafana-data`, `loki-data`, `prometheus-data` (short names, potentially superseded by `ai-folder_*` variants)
- `mkt-solution_grafanadata`, `mkt-solution_ollamadata`, `mkt-solution_pgdata`, `mkt-solution_prometheusdata`, `mkt-solution_qdrantdata`, `mkt-solution_redisdata` (6 vols, likely brandmatik ancestor)
- `mkt-stack_grafana_data`, `mkt-stack_mailpit_data`, `mkt-stack_minio_data`, `mkt-stack_pgadmin_data`, `mkt-stack_postgres_data`, `mkt-stack_prometheus_data`, `mkt-stack_redis_data`, `mkt-stack_redisinsight_data` (8 vols)
- `ollama-data` (short name — `ollama` volume is the live one)
- `prod-*` (27 volumes, entire `prod-stack` replica: chromadb/devops-tools-config/gitea/gitea-runner/gitlab x4/grafana/jenkins x4/loki/minio/nexus/ollama/open-webui/postgres/prometheus/redis/redmine x4/sonarqube x4/splunk x2/trivy)
- `taskflow_grafana_data`, `taskflow_postgres_data`, `taskflow_prometheus_data`, `taskflow_redis_data` (4 vols — declared in a different taskflow compose variant; current taskflow compose uses internal networking against `global-infra-net` postgres/redis)
- Plus ~500 `runner-*` GitLab CI cache volumes (see Orphans §11).

---

## 7. Networks

All networks enumerated via `docker network ls` + `docker network inspect`. Attachment counts below are containers attached per network.

| Network | Driver | Scope | Attached containers | Purpose |
| --- | --- | --- | --- | --- |
| `bridge` | bridge | local | _system default_ | _standard Docker_ |
| `host` | host | local | _system host_ | _host networking_ |
| `none` | null | local | _system null_ | _no networking_ |
| `ai-platform-net` | bridge | local | **30** (all infra-stack except node-exporter/cadvisor/grafana/dcgm-exporter/devops-tools-backend/chatbot-portal/taskflow-* — i.e. jira+postgres, loki, gitea-runner, jaeger, vault, nginx-proxy, gitea-server, gitlab-server, jenkins-master, prometheus, chromadb, chromadb-admin, ai-postgres, jenkins-agent-2, ai-sonar-db, vault-unseal, qdrant, promtail, ai-sonarqube, ai-nexus, redis, ollama, jira-postgres, jenkins-agent-3, minio, redmine, ai-splunk, gitlab-runner, jenkins-agent-1, trivy-server) | infra-stack internal platform bus |
| `brandmatik_brandmatik-net` | bridge | local | **13** (all brandmatik services) | brandmatik internal |
| `chaos-platform-setup_chaos_network` | bridge | local | **18** (all chaos services) | chaos-platform internal |
| `gitlab-net` | bridge | local | **13** (nginx-proxy, gitlab-server, jenkins-master, ai-postgres, jenkins-agent-2, ai-sonarqube, ai-nexus, redis, jenkins-agent-3, minio, ai-splunk, gitlab-runner, jenkins-agent-1) | GitLab<->CI plane |
| `global-infra-net` | bridge | local | **37** (cross-project hub — all of infra-stack majors + dev-stack's devops-tools-backend + chatbot-portal + all 5 taskflow services) | **CRITICAL: cross-stack bridge** connecting dev-stack/taskflow to infra-stack backends |
| `jenkins-net` | bridge | local | **5** (nginx-proxy, jenkins-master, jenkins-agents x3) | Jenkins controller<->agent |
| `kind` | bridge | local | **3** (desktop-control-plane, kind-cloud-provider, kind-registry-mirror) | docker-desktop K8s internal |
| `monitoring-network` | bridge | local | **22** (grafana, loki, jaeger, nginx-proxy, gitlab-server, jenkins-master, prometheus, ai-postgres, dcgm-exporter, jenkins-agent-2, ai-sonar-db, cadvisor, promtail, ai-sonarqube, ai-nexus, redis, jenkins-agent-3, minio, node-exporter, ai-splunk, gitlab-runner, jenkins-agent-1) | Observability stack |
| `ticketing-net` | bridge | local | **5** (jira, nginx-proxy, redmine-db, jira-postgres, redmine) | Jira + Redmine isolation |

> The container-to-multiple-networks pattern is heavy — e.g. `ai-nexus` is on `ai-platform-net`, `gitlab-net`, `global-infra-net`, `monitoring-network` (4 networks). That's fine but means when the portal wires service discovery it should pick the network with the narrowest fanout (usually `global-infra-net`, since dev-stack/taskflow are only on that one).

---

## 8. Kubernetes on docker-desktop

`kubectl` failed initially because no default kubeconfig lookup — `--kubeconfig=/c/Users/deepak/.kube/config` recovered. The `docker-desktop` context is registered and points at `https://127.0.0.1:50537` (Docker Desktop's kube API). API version reports **`v1.34.3`** (Kubernetes 1.34).

The cluster is a **single-node kind-style** cluster (`desktop-control-plane`), which is the new Docker Desktop Kubernetes runtime (kind-based). `kindnet` CNI is installed (not `calico`/`cilium`).

### Namespaces

```
chaos-system         Active   9d
default              Active   9d
kube-node-lease      Active   9d
kube-public          Active   9d
kube-system          Active   9d
local-path-storage   Active   9d
target-apps          Active   9d
```

### Pods

20 pods total; all Running. Workloads (non-system):

| Namespace | Pod | Ready | Age | Image / Purpose |
| --- | --- | --- | --- | --- |
| chaos-system | chaos-agent-599d8579b4-4pgpg | 1/1 | 9d | Cluster-side chaos agent (pair of the compose `chaos-agent`) |
| target-apps | checkout-service (×3) | 1/1 | 9d | Chaos target — demo microservice |
| target-apps | inventory-service (×3) | 1/1 | 9d | Chaos target |
| target-apps | payment-service (×3) | 1/1 | 9d | Chaos target |

System pods (kube-system + local-path-storage): coredns ×2, etcd, kindnet, kube-apiserver, kube-controller-manager, kube-proxy, kube-scheduler, local-path-provisioner (9 total). All Running.

### Services

```
default       kubernetes          ClusterIP   10.96.0.1       443/TCP
kube-system   kube-dns            ClusterIP   10.96.0.10      53/UDP,53/TCP,9153/TCP
target-apps   checkout-service    ClusterIP   10.96.223.213   80/TCP
target-apps   inventory-service   ClusterIP   10.96.122.69    80/TCP
target-apps   payment-service     ClusterIP   10.96.247.229   80/TCP
```

**No ingresses. No PVCs. No PVs. No LoadBalancers.** StorageClass is `local-path` (via `local-path-provisioner`), not `hostpath`.

Note: Pod restart counts are `15 (48m ago)` — every Docker Desktop restart re-creates the control-plane container which counts as a restart. Not a health concern.

---

## 9. Tool availability matrix

**KEY DELIVERABLE** — portal catalog. Reachability tested with `curl -sS -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:<port>/` unless noted. HTTP 000 = TCP refused or timeout (non-HTTP port). Databases tested with `pg_isready` / `redis-cli ping`. Ollama with `/api/tags`. Chroma with `/api/v2/heartbeat`.

| Tool | Compose project | Container | Image | Host port | Internal port | Reachability | Health label | Primary volume(s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **DevOps tools backend** (FastAPI) | dev-stack | devops-tools-backend | dev-stack-devops-tools-backend:local | 8003 | 8003 | HTTP **200** at `/` | healthy | `dev-stack_devops-tools-config` |
| **Chatbot portal** (Nginx SPA) | dev-stack | chatbot-portal | dev-stack-chatbot-portal:local | 3005 | 3001 | HTTP **200** at `/` (UI responds fine) | **UNHEALTHY** (see §10) | *stateless* |
| **Ollama** (LLM runtime, GPU) | infra-stack | ollama | ollama/ollama:latest | 11434 | 11434 | HTTP **200**; `/api/tags` returns 3+ models incl. `pipeline-generator-v5:latest` (20.2 GB) and `qwen3:32b` | (no HEALTHCHECK) | `ollama` (23.4 GB) |
| **ChromaDB** | infra-stack | chromadb | chromadb/chroma:latest | 8005 | 8000 | HTTP **200** on `/api/v2/heartbeat` (v1 deprecated) | (no HEALTHCHECK) | `chromadb-data` (1.1 MB) |
| **ChromaDB Admin UI** | infra-stack | chromadb-admin | sanderdw/chromadb-admin:latest | 3001 | 3000 | HTTP **200** at `/` | (no HEALTHCHECK) | *stateless* |
| **Qdrant** (infra) | infra-stack | qdrant | qdrant/qdrant:v1.12.5 | 6333 | 6333 | HTTP **200** on `/`; `/healthz`=`healthz check passed` | healthy | `qdrant-data` (20 KB, empty) |
| **Qdrant gRPC** (infra) | infra-stack | qdrant | qdrant/qdrant:v1.12.5 | 6334 | 6334 | TCP gRPC; HTTP test returns 000 | healthy | shares above |
| **Qdrant** (brandmatik) | brandmatik | brandmatik-qdrant | qdrant/qdrant:v1.12.5 | 6335 | 6333 | HTTP **200**; `/healthz` ok | healthy | `brandmatik_brandmatik-qdrant` (20 KB) |
| **Qdrant gRPC** (brandmatik) | brandmatik | brandmatik-qdrant | qdrant/qdrant:v1.12.5 | 6336 | 6334 | TCP gRPC (000 to HTTP) | healthy | shares above |
| **Postgres** (infra) | infra-stack | ai-postgres | postgres:15-alpine | 5432 | 5432 | `pg_isready` = **accepting connections** | healthy | `postgres-data` (76.6 MB) |
| **Postgres** (jira) | infra-stack | jira-postgres | postgres:15 | internal only | 5432 | `pg_isready` works via exec | healthy | `devops-tools-backend_jira_postgres_data` (84.9 MB) |
| **Postgres** (sonar) | infra-stack | ai-sonar-db | postgres:15-alpine | internal only | 5432 | `pg_isready` via exec | healthy | `sonarqube-postgres-data` (132.3 MB) |
| **Postgres** (redmine) | infra-stack | redmine-db | postgres:15-alpine | internal only | 5432 | _not probed, healthy per label_ | healthy | `plane_redmine-db-data` (48.9 MB) |
| **Postgres** (brandmatik) | brandmatik | brandmatik-postgres | postgres:16-alpine | 5433 | 5432 | `pg_isready` = accepting | healthy | `brandmatik_brandmatik-pgdata` (77.4 MB) |
| **Postgres** (chaos) | chaos-platform-setup | chaos-postgres | postgres:16-alpine | 15432 | 5432 | `pg_isready` = accepting | healthy | `chaos-platform-setup_postgres_data` (66.4 MB) |
| **Redis** (infra) | infra-stack | redis | (image-id ee64a64eaab6) | 6379 | 6379 | `redis-cli ping` = **PONG** | healthy | `redis-data` (20 KB) |
| **Redis** (brandmatik) | brandmatik | brandmatik-redis | redis:7.4-alpine | 6380 | 6379 | `redis-cli ping` = PONG | healthy | `brandmatik_brandmatik-redis` (2.4 MB) |
| **Redis** (chaos) | chaos-platform-setup | chaos-redis | redis:7-alpine | 16379 | 6379 | `redis-cli ping` = PONG | healthy | `chaos-platform-setup_redis_data` (12 KB) |
| **Grafana** (primary) | infra-stack | grafana | image-id 9e1e77ade304 | **3000** | 3000 | HTTP **301** → `/login` (healthy behaviour) | healthy | `ai-folder_grafana-data` (145.6 MB) |
| **Grafana** (chaos) | chaos-platform-setup | chaos-grafana | grafana/grafana:latest | 13000 | 3000 | HTTP **302** → login | healthy | `chaos-platform-setup_grafana_data` (50.6 MB) |
| **Prometheus** (primary) | infra-stack | prometheus | image-id 1f0f50f06aca | 9090 | 9090 | HTTP **302** → `/query`; `/-/healthy` = 404 (wrong path); `/query` = 200 | (no HEALTHCHECK) | `ai-folder_prometheus-data` (1.3 GB) |
| **Prometheus** (chaos) | chaos-platform-setup | chaos-prometheus | prom/prometheus:latest | 19090 | 9090 | HTTP **302** → query | healthy | `chaos-platform-setup_prometheus_data` (70.9 MB) |
| **Loki** | infra-stack | loki | grafana/loki:latest | 3100 | 3100 | HTTP 404 at `/`; `/ready` = "Ingester not ready: waiting for 15s after being ready" (transient startup) | (no HEALTHCHECK) | `ai-folder_loki-data` (395.2 MB) |
| **Jaeger** | infra-stack | jaeger | jaegertracing/all-in-one:latest | 16686 (UI), 14268 (collector) | same | HTTP **200** at `/` (UI); collector `/`=404 which is correct | healthy | *in-memory* (all-in-one) |
| **Node Exporter** | infra-stack | node-exporter | prom/node-exporter:latest | 9100 | 9100 | HTTP **200** at `/` | healthy | *stateless* |
| **cAdvisor** | infra-stack | cadvisor | gcr.io/cadvisor/cadvisor:latest | 8182 | 8080 | HTTP **307** → `/containers/` | healthy | *stateless* |
| **dcgm-exporter** (GPU metrics) | infra-stack | dcgm-exporter | nvidia/dcgm-exporter:3.3.8-3.6.0-ubuntu22.04 | 9400 | 9400 | HTTP **200** at `/` (metrics) | (no HEALTHCHECK) | *stateless* |
| **Jenkins master** | infra-stack | jenkins-master | jenkins/jenkins:lts | 8080 | 8080 | HTTP **404** at `/` (Jenkins responds but no root route); `/login` would be 200 | healthy | `clawd_jenkins-data` |
| **Jenkins agent tunnel** | infra-stack | jenkins-master | — | 50000 | 50000 | HTTP **200** at `/` | — | — |
| **Jenkins agent 1** | infra-stack | jenkins-agent-1 | jenkins/inbound-agent:latest | _none_ | _N/A_ | N/A (agent-only) | (no HEALTHCHECK) | `clawd_jenkins-agent-1-data` |
| **Jenkins agent 2** | infra-stack | jenkins-agent-2 | jenkins/inbound-agent:latest | _none_ | _N/A_ | N/A | (no HEALTHCHECK) | `clawd_jenkins-agent-2-data` |
| **Jenkins agent 3** | infra-stack | jenkins-agent-3 | jenkins/inbound-agent:latest | _none_ | _N/A_ | N/A | (no HEALTHCHECK) | `clawd_jenkins-agent-3-data` |
| **GitLab CE** | infra-stack | gitlab-server | gitlab/gitlab-ce:latest | 8929 (web), 2224 (SSH) | 80, 22 | HTTP **404** at `/` (GitLab returns 404 for unknown paths; `/users/sign_in` → 200) | healthy | (external host mount, verify in compose — `ai-lab_gitlab_*`/`brandmatik-infra_gitlab-*`/`prod-gitlab-*` variants exist) |
| **GitLab Runner** | infra-stack | gitlab-runner | gitlab/gitlab-runner:latest | _none_ | _N/A_ | N/A | (no HEALTHCHECK) | (external host mount) |
| **Gitea** | infra-stack | gitea-server | gitea/gitea:latest | 3002 (web), 2222 (SSH) | 3000, 22 | HTTP **200** at `/` | healthy | `gitea-setup_gitea-data` (56.6 MB) |
| **Gitea Act Runner** | infra-stack | gitea-runner | localhost:5001/apm-repo/demo/gitea-act-runner:latest | _none_ | _N/A_ | N/A | (no HEALTHCHECK) | `gitea-setup_gitea-runner-data` (21.1 MB) |
| **Jira** | infra-stack | jira | atlassian/jira-software:9.12 | 8180 | 8080 | HTTP **200** at `/` | (no HEALTHCHECK) | `devops-tools-backend_jira_data` (972.5 MB) |
| **Redmine** | infra-stack | redmine | redmine:5-alpine | 8090 | 3000 | HTTP **200** at `/` | healthy | `plane_redmine-data` / `plane_redmine-plugins` / `plane_redmine-themes` |
| **SonarQube** | infra-stack | ai-sonarqube | sonarqube:latest | 9002 | 9000 | HTTP **200** at `/` | healthy | `sonarqube-data` (327.7 MB) + extensions + logs |
| **Nexus** | infra-stack | ai-nexus | sonatype/nexus3:latest | 8181, 5001 (Docker-reg) | 8081, 5001 | HTTP **200** at `/` (8181); HTTP 400 on `/` (5001 Docker-registry, correct) | (no HEALTHCHECK) | `nexus-data` (**38.2 GB**) |
| **Trivy Server** | infra-stack | trivy-server | aquasec/trivy:latest | 8183 | 8080 | HTTP **404** at `/` (Trivy has no root route; `/healthz` may work) | (no HEALTHCHECK) | `trivy-cache` (1.0 GB) |
| **Vault** | infra-stack | vault | hashicorp/vault:1.15 | 8200 | 8200 | HTTP **307** → `/ui/` | healthy | `infra-stack_vault-data` (4 KB — looks fresh) + `vault-data` (older alias) |
| **Vault Unseal** (sidecar) | infra-stack | vault-unseal | hashicorp/vault:1.15 | _internal only_ | 8200 | N/A | (no HEALTHCHECK) | *shared w/ vault* |
| **MinIO** (primary) | infra-stack | minio | minio/minio | 9000 (S3 API), 9001 (console) | 9000/9001 | HTTP **403** at 9000 (expected — S3 auth); HTTP 200 implied at 9001 (not probed) | healthy | `minio-data` (232 KB) |
| **MinIO** (chaos) | chaos-platform-setup | chaos-minio | minio/minio:latest | 19000 (S3), 19001 (console) | 9000/9001 | HTTP **403** at 19000 (correct); HTTP 200 at 19001 | healthy | `chaos-platform-setup_minio_data` (136 KB) |
| **Splunk** | infra-stack | ai-splunk | splunk/splunk:latest | 10000 (web), 8088 (HEC) | 8000, 8088 | HTTP **303** at 10000/ (login redirect); HEC on 8088 returns `000` (HTTPS-only — `https://localhost:8088/services/collector/health` → `{"text":"HEC is healthy"}`) | healthy | `prod-splunk-etc` (1.2 GB) + `prod-splunk-var` (1.6 GB) — note `prod-*` name but live-mounted |
| **Nginx proxy** | infra-stack | nginx-proxy | nginx:alpine | 8443 | 80 | HTTP **200** at `/` | healthy | *stateless* |
| **Promtail** | infra-stack | promtail | grafana/promtail:latest | _none_ | _N/A_ | N/A (agent → loki) | (no HEALTHCHECK) | *config-only* |
| **Chaos API Gateway** | chaos-platform-setup | chaos-api-gateway | chaos-platform-setup-api-gateway (local) | 28080 | 8080 | HTTP **404** at `/` (no root route defined) | healthy | *stateless* |
| **Chaos Auth Service** | chaos-platform-setup | chaos-auth-service | chaos-platform-setup-auth-service | 28081 | 8081 | HTTP **404** at `/` | healthy | *stateless* |
| **Chaos Experiment Engine** | chaos-platform-setup | chaos-experiment-engine | chaos-platform-setup-experiment-engine | 28082 | 8082 | HTTP **404** at `/` | healthy | *stateless* |
| **Chaos Telemetry Aggregator** | chaos-platform-setup | chaos-telemetry-aggregator | chaos-platform-setup-telemetry-aggregator | 28083, 50051 | 8083, 50051 | HTTP **404** at `/` (HTTP); gRPC on 50051 (000 via curl) | healthy | *stateless* |
| **Chaos AI Engine** | chaos-platform-setup | chaos-ai-engine | chaos-platform-setup-ai-engine | 28084 | 8084 | HTTP **404** at `/` | healthy | *stateless* |
| **Chaos Report Service** | chaos-platform-setup | chaos-report-service | chaos-platform-setup-report-service | 28085 | 8085 | HTTP **404** at `/` | healthy | *stateless* |
| **Chaos Notification Service** | chaos-platform-setup | chaos-notification-service | chaos-platform-setup-notification-service | 28086 | 8086 | HTTP **404** at `/` | healthy | *stateless* |
| **Chaos Target App 1** | chaos-platform-setup | chaos-target-app-1 | chaos-platform-setup-target-app-1 | 28090 | 8090 | HTTP **200** at `/` | healthy | *stateless* |
| **Chaos Target App 2** | chaos-platform-setup | chaos-target-app-2 | chaos-platform-setup-target-app-2 | 28091 | 8090 | HTTP **200** at `/` | healthy | *stateless* |
| **Chaos Target App 3** | chaos-platform-setup | chaos-target-app-3 | chaos-platform-setup-target-app-3 | 28092 | 8090 | HTTP **200** at `/` | healthy | *stateless* |
| **Chaos Portal UI** | chaos-platform-setup | chaos-portal-ui | chaos-platform-setup-portal-ui | 13001 | 3001 | HTTP **200** at `/` | healthy | *stateless* |
| **Chaos Credentials Dashboard** | chaos-platform-setup | chaos-credentials-dashboard | chaos-platform-setup-credentials-dashboard | 9091 | 9091 | HTTP **200** at `/` | healthy | *stateless* |
| **Chaos NATS** | chaos-platform-setup | chaos-nats | nats:2.10-alpine | 4222 (client), 8222 (monitor) | 4222, 8222 | NATS proto on 4222 (000); HTTP **200** on 8222 monitor | healthy | *ephemeral* |
| **brandmatik API Gateway** | brandmatik | brandmatik-api-gateway | localhost:8082/brandmatik/...:latest | 8100 | 8000 | HTTP **200** | healthy | *stateless* |
| **brandmatik trend-collector** | brandmatik | brandmatik-trend-collector | ... | 8101 | 8001 | HTTP **200** | healthy | *stateless* |
| **brandmatik scoring-engine** | brandmatik | brandmatik-scoring-engine | ... | 8102 | 8002 | HTTP **200** | healthy | *stateless* |
| **brandmatik content-generator** | brandmatik | brandmatik-content-generator | ... | 8103 | 8003 | HTTP **200** | healthy | *stateless* |
| **brandmatik business-service** | brandmatik | brandmatik-business-service | ... | 8104 | 8004 | HTTP **200** | healthy | *stateless* |
| **brandmatik posting-service** | brandmatik | brandmatik-posting-service | ... | 8105 | 8005 | HTTP **200** | healthy | *stateless* |
| **brandmatik analytics-service** | brandmatik | brandmatik-analytics-service | ... | 8106 | 8006 | HTTP **200** | healthy | *stateless* |
| **brandmatik feedback-service** | brandmatik | brandmatik-feedback-service | ... | 8107 | 8007 | HTTP **200** | healthy | *stateless* |
| **brandmatik notification-service** | brandmatik | brandmatik-notification-service | ... | 8108 | 8008 | HTTP **200** | healthy | *stateless* |
| **brandmatik mock-social-poster** | brandmatik | brandmatik-mock-social-poster | ... | 8110 | 8010 | HTTP **200** | healthy | *stateless* |
| **taskflow API Gateway** | taskflow | taskflow-api-gateway | taskflow-api-gateway:local | 18080 | 8080 | HTTP **404** at `/` (Spring Boot no root) | healthy | *stateless* |
| **taskflow Auth Service** | taskflow | taskflow-auth-service | taskflow-auth-service:local | 18081 | 8080 | HTTP **404** at `/` | healthy | *stateless* |
| **taskflow Task Service** | taskflow | taskflow-task-service | taskflow-task-service:local | 18082 | 8080 | HTTP **404** at `/` | healthy | *stateless* |
| **taskflow Notification Service** | taskflow | taskflow-notification-service | taskflow-notification-service:local | 18083 | 8080 | HTTP **404** at `/` | healthy | *stateless* |
| **taskflow MailHog** | taskflow | taskflow-mailhog | mailhog/mailhog:latest | 8025 | 8025 | HTTP **200** at `/` (UI) | (no HEALTHCHECK) | *ephemeral* |

**Total tool rows**: 67.

Notes on "unexpected 404":
- Spring Boot apps (Chaos services, taskflow services) commonly return 404 at `/` — try `/actuator/health` via the portal.
- Trivy API responds at `/healthz`, not `/`.
- Splunk HEC is HTTPS only on 8088 (correctly returned 000 via plain HTTP, confirmed `HEC is healthy` via HTTPS).

---

## 10. chatbot-portal diagnosis

### Evidence

1. `docker inspect chatbot-portal --format '{{json .State}}'`:
   - `Status: running`, `Running: true`.
   - `Health.Status: unhealthy`, `FailingStreak: 99`.
   - Every log entry: `wget: can't connect to remote host: Connection refused` (exit 1).

2. Healthcheck config:
   ```json
   {"Test":["CMD","wget","-qO-","http://localhost:3001/"],"Interval":30s,"Timeout":5s,"StartPeriod":10s,"Retries":3}
   ```

3. `docker exec chatbot-portal ss -tlnp`:
   ```
   tcp 0 0 0.0.0.0:3001 0.0.0.0:* LISTEN 1/nginx: master pro
   ```
   Nginx is listening on IPv4 `0.0.0.0:3001` only — no IPv6 bind.

4. Inside-container IPv4 vs IPv6 test:
   - `wget -qO- http://127.0.0.1:3001/` → returns HTML, exit 0 ✓
   - `wget -qO- http://[::1]:3001/` → "Connection refused", exit 0 (exit code reset by busybox wget, but body is empty) ✗

5. `/etc/hosts` inside container:
   ```
   127.0.0.1  localhost
   ::1        localhost ip6-localhost ip6-loopback
   ```
   Both entries present. BusyBox wget resolves `localhost` via `/etc/hosts` and **tries IPv6 first**; nginx isn't listening on `::1:3001` so the probe fails.

6. Nginx config (`/etc/nginx/conf.d/default.conf`): `listen 3001;` — IPv4 only; no `listen [::]:3001;`.

7. External reachability from host via mapped port 3005: HTTP **200** at `/`, HTTP **200** at `/health` returning `{"status":"healthy","version":"1.0.0"}`. **The actual service is fully working** — only the self-healthcheck is broken.

### Root cause

**IPv6-first name resolution in BusyBox wget inside the chatbot-portal image, against an nginx bound only to IPv4.** Classic dual-stack mismatch.

### Recommended fixes (NOT APPLIED per read-only constraint)

Three options, in order of correctness:

**Option A — force IPv4 in the healthcheck (minimal, Dockerfile/compose only, no image rebuild if using compose override):**
```yaml
services:
  chatbot-portal:
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:3001/"]
      interval: 30s
      timeout: 5s
      start_period: 10s
      retries: 3
```

**Option B — make nginx listen on IPv6 as well (Dockerfile config change, dual-stack):** Add `listen [::]:3001;` next to `listen 3001;` in `/etc/nginx/conf.d/default.conf`, or set `listen 3001 ipv6only=off;` on a single line. Rebuilds image.

**Option C — drop to curl and add `--ipv4`:** requires installing curl in the image (heavier).

**Recommended**: Option A (compose healthcheck override) is zero-rebuild and safe. Option B is the "correct" long-term fix — IPv6 should be a first-class citizen.

File to edit for Option A: `D:\Repos\ai-folder\dev-stack\infrastructure\docker-compose.yml` (healthcheck stanza under `chatbot-portal`).  
File to edit for Option B: the nginx config sitting in the chatbot-portal build context, typically `D:\Repos\ai-folder\dev-stack\infrastructure\chatbot-portal\nginx.conf` or similar — verify location by reading the dev-stack compose `build:` stanza before editing.

---

## 11. Orphans & cleanup candidates

> **DO NOT execute removal during this read-only pass.** Listing only.

### (a) Containers with empty compose project label

None. Every container has a `com.docker.compose.project` label; the three non-compose containers (`desktop-control-plane`, `kind-cloud-provider`, `kind-registry-mirror`) are K8s runtime internals (should not be touched).

### (b) Volumes not mounted by any running container (RefCount=0 from running set)

**High-value retained volumes** (may be worth archiving before any prune):

| Volume | Size (if measured) | Likely data | Action |
| --- | --- | --- | --- |
| `prod-splunk-etc` | 1.2 GB | Prod-stack Splunk config (but currently live-mounted by `ai-splunk`!) | DO NOT touch — still in use |
| `prod-splunk-var` | 1.6 GB | Prod-stack Splunk indexes (live-mounted) | DO NOT touch |
| `ai-lab_gitlab_data` / `ai-lab_gitlab_logs` / `ai-lab_gitlab_config` | unknown | Legacy ai-lab GitLab state | Archive then prune (confirmed not in use) |
| `brandmatik-infra_nexus-data` | unknown | Local Nexus @ 8082 (brandmatik image registry target) | KEEP — images reference it |
| `mkt-solution_*` (6 vols) | unknown | Predecessor of brandmatik | Archive then prune |
| `mkt-stack_*` (8 vols) | unknown | Unknown project | Archive then prune after confirming |
| `prod-*` non-splunk (25 vols) | unknown | Cold prod-stack replica | Archive then prune (large set) |

**Safe-to-prune noise** (run `docker volume prune` only if you want them gone — no data):

| Pattern | Count | Size impact | Notes |
| --- | --- | --- | --- |
| `runner-*` GitLab CI cache | ~500 | likely many GB | Per-job caches; trivially rebuildable. Main noise source. |
| `GITEA-ACTIONS-TASK-*` | 4 | small | Gitea Actions run caches. Safe. |
| 621 anonymous 64-hex volumes | 621 | unknown individual | Result of container-recreate cycles where image `VOLUME` directives create anon vols. Many belong to now-deleted containers. `docker volume prune --filter 'label!=keep'` would remove them. |

### (c) Images with no running container AND > 90 days old

Representative examples (not exhaustive — the engine carries **1,040 images**; 627 total IDs after tag dedup). Sample from the "2 months ago" bucket:

| Image | Age | Size | Status |
| --- | --- | --- | --- |
| `localhost:5001/apm-repo/demo/java-springboot-api` (7 tags: 1.0.14/15/18/20/21, latest, 1.0.release-18) | 2mo | 442MB each (shared layers) | Old CI build cache — prune candidate |
| `localhost:5001/apm-repo/demo/gitea-act-runner:latest` | 2mo | 109MB | **IN USE** by `gitea-runner` — keep |
| `backend-devops-tools-backend:latest` | 2mo | 987MB | Legacy build of current dev-stack backend — prune candidate |
| `infrastructure-devops-tools-backend:latest` | 2mo | 987MB | Legacy build — prune candidate |
| `mongo:7` | 2mo | 1.18GB | No running Mongo container — prune candidate if no future need |
| `kong:3.9` | 2mo | 534MB | No running Kong — prune candidate |
| `ghcr.io/fluxcd/*` (4 images) | 2mo | ~650MB total | No Flux running locally — prune candidate if K8s doesn't need |
| `harness/le-nextgen-signed:1.13.0` | 2mo | **5.23GB** | Harness delegate — prune candidate |
| `kong/kubernetes-ingress-controller:3.5` | 2mo | 98.8MB | No K8s ingress installed — prune candidate |
| `quay.io/strimzi/operator:0.50.1` | 2mo | 757MB | Kafka operator — prune candidate |
| `releases-docker.jfrog.io/jfrog/artifactory-oss:latest` | 2mo | **4.34GB** | Unused — prune candidate (heavy) |
| `ollama/ollama:0.16.2` | 2mo | 8.99GB | Old Ollama (live runs `ollama/ollama:latest`) — prune candidate but verify digest |
| `mkt-stack-*` (7 images) | 2mo | ~5.3GB | Mkt-stack legacy — prune candidate |
| `opensearchproject/opensearch-dashboards:3.5.0` | 2mo | 2.96GB | No OpenSearch running — prune candidate |

Estimated recoverable space from aggressive image prune: **~50-80 GB** across those listed and similar.

**Recommended cleanup sequence (run AFTER backup/archive decisions, not in this read-only pass):**

1. `docker volume ls --filter 'name=runner-' -q | xargs docker volume rm` — safest first cut (~500 vols, frees CI caches).
2. Review and rm `mkt-solution_*`, `mkt-stack_*`, `ai-lab_*` after confirming no archive needed.
3. `docker image prune -a --filter 'until=2160h'` (90 days) — after confirming nothing critical older than 90d is needed.
4. `docker volume prune` (anonymous only by default) — safe last pass.

---

## 12. Gaps & recommendations

### Portal catalog wiring

For the portal rebuild, the **Tool Availability Matrix in §9 is the authoritative source**. Each row has the exact field set the portal needs: `tool`, `compose_project`, `container`, `image`, `host_port`, `internal_port`, `health`, `volume(s)`, `reachability_test` result.

Recommendations for the portal catalog schema:

1. **Probe URL must be configurable per tool**, not `/`. Most services return 404 at `/` and 200 at `/login`, `/healthz`, `/api/v2/heartbeat`, `/actuator/health`, etc. Mapping in §9 gives you the right probe for each.
2. **Distinguish "container healthy" vs "service reachable"**. Chatbot-portal is the canonical counter-example: Docker health=unhealthy, service health=200.
3. **Include the network on which the portal would proxy**. `global-infra-net` is the super-hub — the portal itself should attach there if it needs to proxy everything.
4. **Map "short-name" volumes (no project prefix) explicitly**. `ollama`, `nexus-data`, `postgres-data`, `redis-data`, `chromadb-data`, `qdrant-data`, `minio-data`, `grafana-data`, `loki-data`, `prometheus-data`, `trivy-cache`, `sonar-data`, `sonarqube-*` etc. are all currently owned by `infra-stack` but pre-date its project naming, hence the lack of prefix.

### Volume-preservation plan

Before any compose `down -v` or `docker volume prune`, the portal's volume-preservation plan should:

1. **Snapshot via `tar` into MinIO or a host path**, not via `docker commit` (which captures the image, not the volume data).
2. **Top-priority volumes to snapshot** (by size and criticality):
   - `nexus-data` (38.2 GB) — all private artifacts
   - `ollama` (23.4 GB) — LLM model cache (incl. `pipeline-generator-v5:latest` 20.2 GB — would be painful to re-pull/re-train)
   - `devops-tools-backend_jira_data` (972.5 MB) — Jira attachments & data dir
   - `trivy-cache` (1.0 GB) — vuln DB (can be rebuilt but takes ~10 min)
   - `ai-folder_prometheus-data` (1.3 GB) — metrics history
   - `prod-splunk-var` (1.6 GB) + `prod-splunk-etc` (1.2 GB) — Splunk indexes
   - `ai-folder_loki-data` (395.2 MB), `ai-folder_grafana-data` (145.6 MB)
   - `sonarqube-data` + `sonarqube-postgres-data` (~460 MB combined) — Sonar state
   - `gitea-setup_gitea-data` (56.6 MB) + `gitea-setup_gitea-runner-data` (21.1 MB)
   - All postgres data volumes: `postgres-data` (76.6 MB), `brandmatik_brandmatik-pgdata` (77.4 MB), `chaos-platform-setup_postgres_data` (66.4 MB), `devops-tools-backend_jira_postgres_data` (84.9 MB), `sonarqube-postgres-data` (132.3 MB), `plane_redmine-db-data` (48.9 MB)
3. **Suggested snapshot command pattern** (NOT to run now):
   ```bash
   docker run --rm \
     -v <vol>:/src:ro \
     -v /mnt/backup/docker-vols:/dst \
     alpine:3.20 tar czf /dst/<vol>-$(date +%F).tgz -C /src .
   ```

### Container-network rationalisation

- `ai-nexus` is on 4 networks, `ai-postgres` on 5, `nginx-proxy` on 6. This is maintenance-hostile. Consider collapsing `monitoring-network` + `ai-platform-net` into `global-infra-net` for docker-desktop-only usage. (Defer — not urgent.)
- `global-infra-net` has 37 attached containers, crossing 5 compose projects. This is the right "shared service bus" for the portal to attach to. Portal backend should join this network (`external: true`) and address other tools by container name.

### Kubernetes drift

- Only `chaos-system`, `target-apps` have non-system pods on the cluster. None of the core DevOps tooling (Jenkins, GitLab, Sonar, etc.) runs as pods — all in compose. For the portal, the K8s integration is only relevant for the chaos platform's in-cluster target apps.
- The cluster uses `local-path` storage class (not Docker Desktop's legacy `hostpath`). Any portal-deployed K8s workload must request `storageClassName: local-path`.

### One-shot container hygiene

- `rbac-init` (created, never started) should either be deleted via `docker compose rm rbac-init` (after verifying it's not blocking something) or started once with `docker start rbac-init`. Compose-side, the restart policy on init jobs should be `no` so they don't endlessly re-queue. Do not touch without investigating the `/rbac-init.sh` content first.
- `vault-init` and `brandmatik-db-migrations` exited 0 — these are correct completed init jobs. Keep (they serve as restart-history evidence for compose idempotency).

### Health-probe consistency (beyond chatbot-portal)

A few tools have **no HEALTHCHECK** declared: `ollama`, `chromadb`, `chromadb-admin`, `prometheus`, `loki`, `promtail`, `gitlab-runner`, `gitea-runner`, `jenkins-agent-1/2/3`, `vault-unseal`, `dcgm-exporter`, `trivy-server`, `nexus`, `taskflow-mailhog`. Portal should consider treating "no healthcheck defined" distinctly from "healthy", and run its own reachability probe per §9.

### Splunk HEC port

HEC (port 8088) is HTTPS-only but exposed on `0.0.0.0:8088` without a protocol indicator. Portal config should note `scheme: https` + `-k` or embed the self-signed CA.

---

### Final summary (files & commands used)

- Inventory file produced: `C:\Users\deepak\ai-folder\docker-desktop-inventory.md` (this document).
- No modifications were made to any container, volume, network, image, or compose file.
- All Docker commands prefixed with `unset DOCKER_HOST && export DOCKER_CONTEXT=desktop-linux`.
- Kubectl commands prefixed with `--kubeconfig=/c/Users/deepak/.kube/config` because the Git Bash shell had no current-context set; the config file does have `current-context: docker-desktop`, so WSL-side or a fresh shell would work natively.
- Key source files discovered for portal wiring (do not edit yet):
  - `D:\Repos\ai-folder\infra-stack\docker-compose.yml` + 7 shards (`ai.yml`, `cicd.yml`, `core.yml`, `monitoring.yml`, `projects.yml`, `quality.yml`, `scm.yml`).
  - `D:\Repos\ai-folder\dev-stack\infrastructure\docker-compose.yml`.
  - `D:\Repos\Mkt-solution\docker-compose.yml`.
  - `C:\Users\deepak\chaos-platform-setup\docker-compose.yml`.
  - `C:\Users\deepak\test-repo\taskflow\docker-compose.yml`.
- Rollback: read-only — no rollback needed. No state changes were made. chatbot-portal fix is **not applied** per scope; fix plan recorded in §10 for the next phase.
