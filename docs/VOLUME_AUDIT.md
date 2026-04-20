# Docker Volume Audit — desktop-linux context

**Audit date:** 2026-04-20
**Docker context:** `desktop-linux`
**Totals:** 809 volumes, 73 running containers, 77 containers total (73 up + 4 exited/created).

**Headline numbers**

| Bucket                                          | Count | Size       |
|-------------------------------------------------|-------|------------|
| **Active** (mounted by a running container)     | 47    | 81.64 GB   |
| **Orphans** (not mounted by any running container) | 762   | 56.72 GB   |
| &nbsp;&nbsp;- named compose/stack volumes (all safe to prune) | 86    | 39.19 GB   |
| &nbsp;&nbsp;- anonymous 64-hex volumes (172 safe + 4 preserve) | 176   | 14.93 GB (13.38 GB safe) |
| &nbsp;&nbsp;- `runner-*-cache-*` GitLab runner caches (all safe) | 500 | 2.60 GB   |
| **Reclaimable if all 3 tiers below are executed** | **758** | **~55.17 GB** |

Of the 762 orphans, **758 are fully dangling** (no container reference at all — safe to prune) and **4 are held by non-running containers** (preserve, total 1.543 GB):
- 2 by stopped vault init containers (`rbac-init`, `vault-init`) — anonymous `/vault/logs` volumes, 0 B each — preserve with the vault toolchain
- 2 by internal Docker Desktop Kubernetes services (`/desktop-control-plane`, `/kind-cloud-provider`) — **DO NOT PRUNE** (holds the Kind K8s cluster node FS, 1.543 GB)

---

## 1. Active volumes (mounted by a running tool container)

Only volumes mounted by a running container are listed. Supporting containers (e.g., `redmine-db`, `jira-postgres`, `ai-sonar-db`, jenkins agents 1/2/3, `vault-unseal`) appear next to the tool they back. `gitlab-server` carries all its state on a host bind mount (`C:/Users/deepak/gitlab_docker/...`), not a docker volume, so it has no rows here.

| Tool (portal id)       | Container name           | Volume                                                                                | Mount point                              | Size     |
|------------------------|--------------------------|---------------------------------------------------------------------------------------|------------------------------------------|----------|
| ollama                 | ollama                   | `ollama`                                                                              | `/root/.ollama`                          | 28.46 GB |
| chromadb               | chromadb                 | `chromadb-data`                                                                       | `/data`                                  | 4.402 MB |
| qdrant                 | qdrant                   | `qdrant-data`                                                                         | `/qdrant/storage`                        | 357 B    |
| jenkins                | jenkins-master           | `clawd_jenkins-data`                                                                  | `/var/jenkins_home`                      | 354.8 MB |
| jenkins (agent 1)      | jenkins-agent-1          | `clawd_jenkins-agent-1-data`                                                          | `/home/jenkins/agent`                    | 40.17 MB |
| jenkins (agent 1)      | jenkins-agent-1          | `80245d001801ffdf6d84fdf650749c7ac776fc9526a98f1c533107aa0c080e6d` (anon)             | `/home/jenkins/.jenkins`                 | 0 B      |
| jenkins (agent 2)      | jenkins-agent-2          | `clawd_jenkins-agent-2-data`                                                          | `/home/jenkins/agent`                    | 40.17 MB |
| jenkins (agent 2)      | jenkins-agent-2          | `553ce4815dbf9a4975dbaa732b2f875955550980eaed80a07e1e677475f4c7dc` (anon)             | `/home/jenkins/.jenkins`                 | 0 B      |
| jenkins (agent 3)      | jenkins-agent-3          | `clawd_jenkins-agent-3-data`                                                          | `/home/jenkins/agent`                    | 40.17 MB |
| jenkins (agent 3)      | jenkins-agent-3          | `41e180dc58a45cd16f9617634de9817139777f324433361caf2b89df642c09cc` (anon)             | `/home/jenkins/.jenkins`                 | 0 B      |
| gitlab-runner          | gitlab-runner            | `ba49bf5e163ce8a9e953ea0693b1b7f758a5950110913a223518ad20c5dc05e8` (anon)              | `/etc/gitlab-runner`                     | 14 B     |
| gitlab-runner          | gitlab-runner            | `49b0178fbdaf2cb1a5846e61b150eb831a168e6bd25124ae6f6bc65c111f177e` (anon)              | `/home/gitlab-runner`                    | 0 B      |
| gitea-runner           | gitea-runner             | `gitea-setup_gitea-runner-data`                                                       | `/data`                                  | 13.66 MB |
| gitea                  | gitea-server             | `gitea-setup_gitea-data`                                                              | `/data`                                  | 23.61 MB |
| sonarqube              | ai-sonarqube             | `sonarqube-data`                                                                      | `/opt/sonarqube/data`                    | 341.6 MB |
| sonarqube              | ai-sonarqube             | `sonarqube-extensions`                                                                | `/opt/sonarqube/extensions`              | 1.017 kB |
| sonarqube              | ai-sonarqube             | `sonarqube-logs`                                                                      | `/opt/sonarqube/logs`                    | 1.577 MB |
| sonarqube              | ai-sonarqube             | `f2056fa4d5b41f6f14c3527f59ad9b49aedebebdc0ac78bdbf451b223fd35db2` (anon)              | `/opt/sonarqube/temp`                    | 313.5 MB |
| sonarqube (db)         | ai-sonar-db              | `sonarqube-postgres-data`                                                             | `/var/lib/postgresql/data`               | 138.5 MB |
| vault                  | vault                    | `vault-data`                                                                          | `/vault/file`                            | 46.23 kB |
| vault                  | vault                    | `956ab49b33dfcdd303df1a235e413ae840af72c41a01d8ab230cce03850b1d5e` (anon)              | `/vault/logs`                            | 0 B      |
| vault (unseal)         | vault-unseal             | `vault-data`                                                                          | `/vault/file`                            | 46.23 kB |
| vault (unseal)         | vault-unseal             | `f92347e571859a14ddb6bda656b4ba3005e255d252bba861664030ecf560be0a` (anon)              | `/vault/logs`                            | 0 B      |
| trivy                  | trivy-server             | `trivy-cache`                                                                         | `/var/lib/trivy`                         | 1.081 GB |
| nexus                  | ai-nexus                 | `nexus-data`                                                                          | `/nexus-data`                            | 40.92 GB |
| grafana                | grafana                  | `ai-folder_grafana-data`                                                              | `/var/lib/grafana`                       | 151.7 MB |
| prometheus             | prometheus               | `ai-folder_prometheus-data`                                                           | `/prometheus`                            | 1.733 GB |
| loki                   | loki                     | `ai-folder_loki-data`                                                                 | `/loki`                                  | 441.3 MB |
| jaeger                 | jaeger                   | `a6bcd5b320ee1a43b76787a569586c9dcb915a948b61e7c60ca56e06fbdd12b0` (anon)              | `/tmp`                                   | 0 B      |
| splunk                 | ai-splunk                | `9dc29ee918744304858a17e8cd0228efe7076d256f699d4d216b1d1df0618624` (anon)              | `/opt/splunk/var`                        | 4.692 GB |
| splunk                 | ai-splunk                | `4ab1508871e7553d3fc1fc3b4c36b8f5829f7ddd10a19524406793aeb42ea9c1` (anon)              | `/opt/splunk/etc`                        | 1.306 GB |
| postgres-ai            | ai-postgres              | `postgres-data`                                                                       | `/var/lib/postgresql/data`               | 80.08 MB |
| redis                  | redis                    | `redis-data`                                                                          | `/data`                                  | 7.358 kB |
| minio                  | minio                    | `minio-data`                                                                          | `/data`                                  | 18.77 kB |
| jira                   | jira                     | `devops-tools-backend_jira_data`                                                      | `/var/atlassian/application-data/jira`   | 1.025 GB |
| jira (db)              | jira-postgres            | `devops-tools-backend_jira_postgres_data`                                             | `/var/lib/postgresql/data`               | 88.78 MB |
| redmine                | redmine                  | `plane_redmine-data`                                                                  | `/usr/src/redmine/files`                 | 0 B      |
| redmine                | redmine                  | `plane_redmine-plugins`                                                               | `/usr/src/redmine/plugins`               | 31 B     |
| redmine                | redmine                  | `plane_redmine-themes`                                                                | `/usr/src/redmine/public/themes`         | 7.363 kB |
| redmine (db)           | redmine-db               | `plane_redmine-db-data`                                                               | `/var/lib/postgresql/data`               | 51.11 MB |
| brandmatik (postgres)  | brandmatik-postgres      | `brandmatik_brandmatik-pgdata`                                                        | `/var/lib/postgresql/data`               | 81.47 MB |
| brandmatik (qdrant)    | brandmatik-qdrant        | `brandmatik_brandmatik-qdrant`                                                        | `/qdrant/storage`                        | 357 B    |
| brandmatik (redis)     | brandmatik-redis         | `brandmatik_brandmatik-redis`                                                         | `/data`                                  | 2.512 MB |
| chaos-platform (pg)    | chaos-postgres           | `chaos-platform-setup_postgres_data`                                                  | `/var/lib/postgresql/data`               | 69.56 MB |
| chaos-platform (redis) | chaos-redis              | `chaos-platform-setup_redis_data`                                                     | `/data`                                  | 5.702 kB |
| chaos-platform (minio) | chaos-minio              | `chaos-platform-setup_minio_data`                                                     | `/data`                                  | 14.38 kB |
| chaos-platform (prom)  | chaos-prometheus         | `chaos-platform-setup_prometheus_data`                                                | `/prometheus`                            | 96.68 MB |
| chaos-platform (graf)  | chaos-grafana            | `chaos-platform-setup_grafana_data`                                                   | `/var/lib/grafana`                       | 51.91 MB |

**Notes**

- `vault-data` is mounted by BOTH `vault` and `vault-unseal`, hence `LINKS=4` in `docker system df -v` (2 running + 2 stopped init containers). Count as one physical volume.
- `gitlab-server` stores ALL its state on a host bind mount at `C:/Users/deepak/gitlab_docker/{config,logs,data}` — it does NOT own a docker volume and therefore never appears here. See the preservation section.
- Tools `promtail`, `cadvisor`, `node-exporter`, `dcgm-exporter`, `nginx-proxy`, `devops-tools-backend`, `chromadb-admin`, `chatbot-portal`, `taskflow-*`, the brandmatik app services, the chaos-platform app services, and the target-app-{1,2,3} containers declare no docker volumes (only bind mounts or ephemeral rootfs).
- 47 unique volumes in use (48 mount entries: `vault-data` is counted once but mounted by two containers).

---

## 2. Orphaned named volumes

Below are the 86 named (non-hex, non-`runner-*`) volumes that are **not mounted by any running container**. Every one of them also shows as dangling under `docker volume ls --filter dangling=true` — no stopped container references them either. Grouped by compose-project prefix.

### 2.1 `mkt-solution_*` — Marketing stack v2 experiment (safe to prune)

| Volume                             | Size      |
|------------------------------------|-----------|
| `mkt-solution_ollamadata`          | 14.83 GB  |
| `mkt-solution_pgdata`              | 76.03 MB  |
| `mkt-solution_qdrantdata`          | 69.48 MB  |
| `mkt-solution_grafanadata`         | 14.61 MB  |
| `mkt-solution_prometheusdata`      | 8.966 MB  |
| `mkt-solution_redisdata`           | 4.774 MB  |

**Verdict:** safe to prune. `mkt-solution` compose project has zero running containers; volumes last touched 2026-02-19. The 14.83 GB ollama model dump is the single biggest reclaim on this host.

### 2.2 `mkt-stack_*` — Earlier marketing stack iteration (safe to prune)

| Volume                             | Size      |
|------------------------------------|-----------|
| `mkt-stack_grafana_data`           | 50.19 MB  |
| `mkt-stack_postgres_data`          | 48.37 MB  |
| `mkt-stack_redisinsight_data`      | 2.224 MB  |
| `mkt-stack_prometheus_data`        | 1.428 MB  |
| `mkt-stack_pgadmin_data`           | 176.5 kB  |
| `mkt-stack_minio_data`             | 29 kB     |
| `mkt-stack_redis_data`             | 23.43 kB  |
| `mkt-stack_mailpit_data`           | 0 B       |

**Verdict:** safe to prune. Superseded by the brandmatik/chaos-platform stacks; no running container in the `mkt-stack` project.

### 2.3 `ai-lab_*` — Retired AI lab compose project (safe to prune)

| Volume                             | Size      |
|------------------------------------|-----------|
| `ai-lab_gitlab_logs`               | 1.273 GB  |
| `ai-lab_prometheus_data`           | 946.5 MB  |
| `ai-lab_gitlab_data`               | 575.9 MB  |
| `ai-lab_loki_data`                 | 352.7 MB  |
| `ai-lab_dind_data`                 | 299.2 MB  |
| `ai-lab_grafana_data`              | 25.17 MB  |
| `ai-lab_gitlab_config`             | 177.7 kB  |
| `ai-lab_gitlab_runner_config`      | 906 B     |
| `ai-lab_ollama_data`               | 468 B     |
| `ai-lab_qdrant_data`               | 357 B     |

**Verdict:** safe to prune. `ai-lab` compose project has been replaced by `infra-stack`; no running container uses any of these. The embedded gitlab volumes are distinct from the current `gitlab-server` bind mount.

### 2.4 `brandmatik-infra_*` — Early brandmatik infra compose (safe to prune)

| Volume                             | Size      |
|------------------------------------|-----------|
| `brandmatik-infra_nexus-data`      | 6.904 GB  |
| `brandmatik-infra_gitlab-logs`     | 1.25 GB   |
| `brandmatik-infra_gitlab-data`     | 253.1 MB  |
| `brandmatik-infra_gitlab-config`   | 177.4 kB  |

**Verdict:** safe to prune. Different compose project from the active `brandmatik` one (which runs without its own gitlab/nexus). Second largest reclaim target after `mkt-solution_ollamadata`.

### 2.5 `brandmatik_*` observability (stale; compose now delegates to infra-stack)

| Volume                                 | Size      |
|----------------------------------------|-----------|
| `brandmatik_brandmatik-grafana`        | 993.8 kB  |
| `brandmatik_brandmatik-prometheus`     | 28.74 MB  |

**Verdict:** safe to prune. The running `brandmatik` project only keeps `brandmatik_brandmatik-{pgdata,qdrant,redis}` wired up (and scrapes metrics via the shared `infra-stack` Prometheus). These are left behind from an older compose that ran its own observability sidecars.

### 2.6 `prod-stack` — former "prod" compose on the dev host (safe to prune)

32 volumes created together on 2026-02-14 under compose project `prod-stack`:

| Volume                               | Size      |
|--------------------------------------|-----------|
| `prod-splunk-var`                    | 1.667 GB  |
| `prod-splunk-etc`                    | 1.306 GB  |
| `prod-open-webui-data`               | 1.117 GB  |
| `prod-trivy-cache`                   | 998.6 MB  |
| `prod-gitlab-data`                   | 963.2 MB  |
| `prod-gitlab-logs`                   | 348 MB    |
| `prod-sonarqube-data`                | 153.1 MB  |
| `prod-jenkins-data`                  | 111.6 MB  |
| `prod-sonarqube-db-data`             | 80.18 MB  |
| `prod-redmine-db-data`               | 50.71 MB  |
| `prod-grafana-data`                  | 50.19 MB  |
| `prod-postgres-data`                 | 47.8 MB   |
| `prod-prometheus-data`               | 19.67 MB  |
| `prod-loki-data`                     | 9.292 MB  |
| `prod-jenkins-agent-1-data`          | 4.233 MB  |
| `prod-jenkins-agent-3-data`          | 4.232 MB  |
| `prod-jenkins-agent-2-data`          | 4.232 MB  |
| `prod-nexus-data`                    | 3.869 MB  |
| `prod-gitea-data`                    | 2.203 MB  |
| `prod-gitlab-config`                 | 182.3 kB  |
| `prod-sonarqube-logs`                | 134.2 kB  |
| `prod-minio-data`                    | 14.38 kB  |
| `prod-redmine-themes`                | 7.363 kB  |
| `prod-sonarqube-extensions`          | 1.007 kB  |
| `prod-ollama-data`                   | 468 B     |
| `prod-redis-data`                    | 264 B     |
| `prod-redmine-plugins`               | 31 B      |
| `prod-gitlab-runner-config`          | 14 B      |
| `prod-redmine-data`                  | 0 B       |
| `prod-gitea-runner-data`             | 0 B       |
| `prod-devops-tools-config`           | 0 B       |
| `prod-chromadb-data`                 | 0 B       |

**Verdict:** safe to prune — `prod-stack` compose project is no longer deployed on this host. All 32 carry `com.docker.compose.project=prod-stack` labels. All real data lives in the active `infra-stack` analogues (e.g., `nexus-data`, `clawd_jenkins-data`, `chromadb-data`).

### 2.7 `taskflow_*` stale observability (safe to prune)

| Volume                             | Size      |
|------------------------------------|-----------|
| `taskflow_postgres_data`           | 80.36 MB  |
| `taskflow_prometheus_data`         | 4.308 MB  |
| `taskflow_grafana_data`            | 989.7 kB  |
| `taskflow_redis_data`              | 88 B      |

**Verdict:** safe to prune. The current `taskflow` compose (gateway + auth + task + notification + mailhog, all running) declares no docker volumes. These four are leftovers from an earlier richer compose iteration.

### 2.8 `GITEA-ACTIONS-TASK-*` — ephemeral CI caches (safe to prune)

| Volume                                                                   | Size      |
|--------------------------------------------------------------------------|-----------|
| `GITEA-ACTIONS-TASK-359_WORKFLOW-CI-CD-Pipeline_JOB-compile`             | 22.42 MB  |
| `GITEA-ACTIONS-TASK-361_WORKFLOW-CI-CD-Pipeline_JOB-compile`             | 49.32 kB  |
| `GITEA-ACTIONS-TASK-359_WORKFLOW-CI-CD-Pipeline_JOB-compile-env`         | 5.229 kB  |
| `GITEA-ACTIONS-TASK-361_WORKFLOW-CI-CD-Pipeline_JOB-compile-env`         | 5.048 kB  |

**Verdict:** safe to prune. Gitea Actions creates volumes per CI job; tasks 359/361 ran on 2026-02-18 and are no longer referenced. New jobs create fresh volumes.

### 2.9 `clawd_jenkins-agent{1,2}-workspace` — stale agent workspaces (safe to prune)

| Volume                                  | Size |
|-----------------------------------------|------|
| `clawd_jenkins-agent1-workspace`        | 0 B  |
| `clawd_jenkins-agent2-workspace`        | 0 B  |

**Verdict:** safe to prune. Different naming pattern from the ACTIVE `clawd_jenkins-agent-{1,2,3}-data` volumes (note the hyphen + numeric suffix), so these are leftovers from an earlier agent compose iteration.

### 2.10 `sonar-*` stand-alone sonarqube volumes (safe to prune)

| Volume                   | Size      |
|--------------------------|-----------|
| `sonar-data`             | 153.1 MB  |
| `sonar-logs`             | 164.6 kB  |
| `sonar-extensions`       | 1.007 kB  |

**Verdict:** safe to prune. Active SonarQube uses `sonarqube-*` (see section 1), not `sonar-*`.

### 2.11 Short-named relics and empty configmap volumes (safe to prune)

| Volume                                      | Size      | Notes                                                 |
|---------------------------------------------|-----------|-------------------------------------------------------|
| `ollama-data`                               | 4.921 GB  | superseded by the active `ollama` volume              |
| `grafana-data`                              | 45.04 MB  | superseded by `ai-folder_grafana-data`                |
| `prometheus-data`                           | 4.695 MB  | superseded by `ai-folder_prometheus-data`             |
| `loki-data`                                 | 16.55 kB  | superseded by `ai-folder_loki-data`                   |
| `devops-tools-config`                       | 0 B       | empty configmap-style leftover                        |
| `backend_devops-tools-config`               | 0 B       | project=`backend` (retired); empty                    |
| `devops-tools-backend_devops-tools-config`  | 0 B       | older devops-tools-backend compose iteration; empty   |
| `dev-stack_devops-tools-config`             | 0 B       | project=`dev-stack` (retired); empty                  |
| `infra-stack_vault-data`                    | 0 B       | wrong prefix — real vault data is plain `vault-data`  |
| `act-toolcache`                             | 0 B       | `act` runner cache — never populated                  |
| `maven-repo-cache`                          | 0 B       | pipeline idea that never shipped                      |

**Verdict:** all safe to prune. Every single one has a strictly-superseded active counterpart (or is 0 B).

---

## 3. Anonymous (hex-named) orphan volumes — aggregate

**Count: 172 dangling anonymous volumes (13.38 GB, safe to prune) + 4 held by non-running containers (1.543 GB, preserve). Total on disk: 14.93 GB.**

Every 64-hex-character volume name means Docker auto-generated it for a container that declared an anonymous volume in its image's `VOLUME` directive (classic culprits: postgres, jenkins, sonarqube, splunk, mysql). When those containers were removed, Docker left the volumes behind. There is NO way to map these back to a tool from the volume name alone.

The 172 dangling entries are safe to clear in one shot. The 4 non-dangling anon volumes to leave alone are:

| Volume (truncated)              | Held by                                                 | Action    |
|---------------------------------|---------------------------------------------------------|-----------|
| `2f9b8588...9be615000`          | stopped `rbac-init` (vault bootstrap)                   | preserve  |
| `5bceb29d...d1f2d637b1`         | exited `vault-init` (vault bootstrap)                   | preserve  |
| `341bb1e3...ead898ec`           | running `/kind-cloud-provider` (Docker Desktop K8s)     | **do not prune** |
| `de8e6608...1ac0a36a`           | running `/desktop-control-plane` (Docker Desktop K8s)   | **do not prune** |

**Recommendation:** prune the 172 dangling anonymous volumes in one batch. Top offenders: one 6.075 GB volume (`ed97c4a4...`, dated 2026-01-17) and one 2.188 GB volume (`6ba17e26...`, dated 2026-01-17), which look like leftover postgres/splunk data from early tests — but any cross-reference has been lost, so the only safe action is to clear them all or keep them all.

---

## 4. Duplicate data-set risk — same tool, multiple volumes

Any tool that has changed compose-project name over time left behind a copy of its data under the old prefix. In every case the current ACTIVE volume holds the real data; the others are orphans.

| Tool / dataset     | ACTIVE volume (keep)                                    | Orphan duplicates (prune candidates)                                                                                                                                                  |
|--------------------|---------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Ollama             | `ollama` (28.46 GB, `/root/.ollama` on container `ollama`) | `ollama-data` (4.92 GB), `mkt-solution_ollamadata` (14.83 GB), `ai-lab_ollama_data` (468 B), `prod-ollama-data` (468 B)                                                               |
| GitLab             | host bind mount `C:/Users/deepak/gitlab_docker/data`    | `ai-lab_gitlab_data` (575.9 MB), `brandmatik-infra_gitlab-data` (253.1 MB), `prod-gitlab-data` (963.2 MB) — **plus the matching logs/config triples**                                 |
| GitLab logs        | (part of same host bind mount under `/var/log/gitlab`)  | `ai-lab_gitlab_logs` (1.273 GB), `brandmatik-infra_gitlab-logs` (1.25 GB), `prod-gitlab-logs` (348 MB)                                                                               |
| Postgres           | `postgres-data` (80.08 MB, `/var/lib/postgresql/data` on `ai-postgres`) | `mkt-solution_pgdata` (76.03 MB), `mkt-stack_postgres_data` (48.37 MB), `prod-postgres-data` (47.8 MB), `taskflow_postgres_data` (80.36 MB)                                           |
| SonarQube data     | `sonarqube-data` (341.6 MB, on `ai-sonarqube`)          | `sonar-data` (153.1 MB), `prod-sonarqube-data` (153.1 MB)                                                                                                                           |
| SonarQube db       | `sonarqube-postgres-data` (138.5 MB, on `ai-sonar-db`)  | `prod-sonarqube-db-data` (80.18 MB)                                                                                                                                                  |
| SonarQube logs     | `sonarqube-logs` (1.577 MB)                              | `sonar-logs` (164.6 kB), `prod-sonarqube-logs` (134.2 kB)                                                                                                                           |
| SonarQube ext      | `sonarqube-extensions` (1.017 kB)                       | `sonar-extensions` (1.007 kB), `prod-sonarqube-extensions` (1.007 kB)                                                                                                               |
| Jenkins master     | `clawd_jenkins-data` (354.8 MB, on `jenkins-master`)    | `prod-jenkins-data` (111.6 MB)                                                                                                                                                       |
| Jenkins agents     | `clawd_jenkins-agent-{1,2,3}-data` (40.17 MB each)      | `clawd_jenkins-agent1-workspace` (0 B), `clawd_jenkins-agent2-workspace` (0 B), `prod-jenkins-agent-{1,2,3}-data` (~4.23 MB each)                                                    |
| Grafana            | `ai-folder_grafana-data` (151.7 MB, on `grafana`)       | `grafana-data` (45.04 MB), `ai-lab_grafana_data` (25.17 MB), `mkt-stack_grafana_data` (50.19 MB), `mkt-solution_grafanadata` (14.61 MB), `prod-grafana-data` (50.19 MB), `brandmatik_brandmatik-grafana` (993.8 kB), `taskflow_grafana_data` (989.7 kB) |
| Prometheus         | `ai-folder_prometheus-data` (1.733 GB, on `prometheus`) | `prometheus-data` (4.695 MB), `ai-lab_prometheus_data` (946.5 MB), `mkt-stack_prometheus_data` (1.428 MB), `mkt-solution_prometheusdata` (8.966 MB), `prod-prometheus-data` (19.67 MB), `brandmatik_brandmatik-prometheus` (28.74 MB), `taskflow_prometheus_data` (4.308 MB) |
| Loki               | `ai-folder_loki-data` (441.3 MB, on `loki`)             | `loki-data` (16.55 kB), `ai-lab_loki_data` (352.7 MB), `prod-loki-data` (9.292 MB)                                                                                                   |
| Redis              | `redis-data` (7.358 kB, on `redis`)                     | `mkt-solution_redisdata` (4.774 MB), `mkt-stack_redis_data` (23.43 kB), `prod-redis-data` (264 B), `taskflow_redis_data` (88 B)                                                      |
| MinIO              | `minio-data` (18.77 kB, on `minio`)                     | `mkt-stack_minio_data` (29 kB), `prod-minio-data` (14.38 kB)                                                                                                                         |
| Nexus              | `nexus-data` (40.92 GB, on `ai-nexus`)                  | `brandmatik-infra_nexus-data` (6.904 GB), `prod-nexus-data` (3.869 MB)                                                                                                               |
| Trivy cache        | `trivy-cache` (1.081 GB, on `trivy-server`)             | `prod-trivy-cache` (998.6 MB)                                                                                                                                                        |
| ChromaDB           | `chromadb-data` (4.402 MB, on `chromadb`)               | `prod-chromadb-data` (0 B)                                                                                                                                                           |
| Qdrant             | `qdrant-data` (357 B, on `qdrant`)                      | `ai-lab_qdrant_data` (357 B), `mkt-solution_qdrantdata` (69.48 MB)                                                                                                                   |
| Redmine data/db    | `plane_redmine-data`, `plane_redmine-db-data`, `plane_redmine-plugins`, `plane_redmine-themes` (all active) | `prod-redmine-data` (0 B), `prod-redmine-db-data` (50.71 MB), `prod-redmine-plugins` (31 B), `prod-redmine-themes` (7.363 kB)                                                        |
| Gitea / Gitea CI   | `gitea-setup_gitea-data` (23.61 MB), `gitea-setup_gitea-runner-data` (13.66 MB) | `prod-gitea-data` (2.203 MB), `prod-gitea-runner-data` (0 B)                                                                                                                         |
| GitLab Runner cfg  | anonymous live volume on `gitlab-runner`                | `ai-lab_gitlab_runner_config` (906 B), `prod-gitlab-runner-config` (14 B)                                                                                                           |
| devops-tools-config| none live (config is now baked into image)              | `devops-tools-config` (0 B), `backend_devops-tools-config` (0 B), `dev-stack_devops-tools-config` (0 B), `devops-tools-backend_devops-tools-config` (0 B), `prod-devops-tools-config` (0 B) |
| Open WebUI data    | none live (not running on this host)                    | `prod-open-webui-data` (1.117 GB)                                                                                                                                                    |

All "orphan duplicates" columns above are safe to prune — every row has been cross-checked against the section 1 active list. The ACTIVE column is the source of truth and is covered in the preservation section below.

---

## 5. Preservation priority (DO NOT PRUNE)

These volumes (and bind mounts) carry live production data. Pruning any of them is equivalent to a data-loss incident.

| Asset                                                             | Carrier                                                 | Why preserve                                              |
|-------------------------------------------------------------------|---------------------------------------------------------|-----------------------------------------------------------|
| `C:/Users/deepak/gitlab_docker/{config,logs,data}` (host bind)    | `gitlab-server` container at `/etc/gitlab`, `/var/log/gitlab`, `/var/opt/gitlab` | All git repos, CI artifacts, user accounts, issues — this IS the GitLab instance |
| `clawd_jenkins-data`                                              | `jenkins-master` at `/var/jenkins_home`                 | Plugins, job configs, build history, credentials           |
| `clawd_jenkins-agent-1-data`, `-2-data`, `-3-data`                 | `jenkins-agent-{1,2,3}` at `/home/jenkins/agent`        | Active agent workspaces                                    |
| `postgres-data`                                                   | `ai-postgres` at `/var/lib/postgresql/data`             | Primary Postgres backing SonarQube and backend apps        |
| `devops-tools-backend_jira_postgres_data`                         | `jira-postgres` at `/var/lib/postgresql/data`           | Jira database                                              |
| `devops-tools-backend_jira_data`                                  | `jira` at `/var/atlassian/application-data/jira`        | Jira app data (projects, issues, attachments)             |
| `plane_redmine-db-data`                                           | `redmine-db` at `/var/lib/postgresql/data`              | Redmine Postgres database                                  |
| `plane_redmine-data`, `plane_redmine-plugins`, `plane_redmine-themes` | `redmine` container                                   | Redmine app data and customization                         |
| `sonarqube-postgres-data`                                         | `ai-sonar-db` at `/var/lib/postgresql/data`             | SonarQube database                                         |
| `sonarqube-data`, `sonarqube-extensions`, `sonarqube-logs`        | `ai-sonarqube`                                          | Quality analysis results, plugins                          |
| `nexus-data`                                                      | `ai-nexus` at `/nexus-data`                             | Actual artifacts — 40.92 GB. Highest-value single volume   |
| `chromadb-data`                                                   | `chromadb` at `/data`                                   | Vector embeddings. Already recovered in a prior task — do NOT touch |
| `vault-data`                                                      | `vault` + `vault-unseal` at `/vault/file`               | Sealed secrets Raft storage. Destructive prune = total vault loss |
| `956ab49b33df...50b1d5e` (vault log anon)                          | `vault` at `/vault/logs`                                | Vault audit log (zero bytes now but receives future audit entries) |
| `f92347e57185...60be0a` (vault-unseal log anon)                    | `vault-unseal` at `/vault/logs`                         | Vault unseal log                                           |
| `2f9b8588...863218ec`, `5bceb29d...1f2d637b1`                      | stopped `rbac-init`, `vault-init` init containers       | Vault bootstrap log volumes — tied to vault start recovery |
| `trivy-cache`                                                     | `trivy-server` at `/var/lib/trivy`                      | Vulnerability DB (1.08 GB) — regeneratable but slow        |
| `gitea-setup_gitea-data`                                          | `gitea-server` at `/data`                               | Gitea repositories and users                               |
| `gitea-setup_gitea-runner-data`                                   | `gitea-runner` at `/data`                               | Runner token + cached artifacts                           |
| `ollama` (the named volume, NOT `ollama-data`)                     | `ollama` at `/root/.ollama`                             | 28.46 GB of downloaded models — expensive to refetch       |
| `ai-folder_prometheus-data`                                       | `prometheus`                                            | 1.733 GB of retained TSDB metrics                          |
| `ai-folder_grafana-data`                                          | `grafana`                                               | Dashboards, users, plugins                                 |
| `ai-folder_loki-data`                                             | `loki`                                                  | 441 MB of retained logs                                    |
| `chaos-platform-setup_{postgres,redis,minio,prometheus,grafana}_data` | chaos-platform containers                              | Chaos engineering state and metrics                        |
| `brandmatik_brandmatik-{pgdata,qdrant,redis}`                      | brandmatik-postgres/qdrant/redis                        | Social analytics platform data                             |
| `9dc29ee918...618624`, `4ab1508871...4ea9c1` (splunk anon)          | `ai-splunk` at `/opt/splunk/{var,etc}`                  | Splunk indexed data + config (5.99 GB combined)            |
| `341bb1e3...ead898ec`, `de8e6608...1ac0a36a`                       | Docker Desktop K8s cluster (`desktop-control-plane`, `kind-cloud-provider`) | **Killing these corrupts Docker Desktop's built-in Kubernetes** |

Anything NOT on this list and NOT in section 1 is a prune candidate. Everything on this list must be left alone even when running `docker volume prune` or `docker system prune --volumes`.

---

## 6. Prune commands — DO NOT RUN; operator executes manually

Three tiers, ordered by increasing risk. Each tier is idempotent — if a volume is already gone the command moves on. None of these touches the section 5 preserve list.

### Tier A — named stale compose orphans (39.19 GB, zero risk)

```bash
# SAFE: mkt-solution compose project is retired; biggest single reclaim here (14.83 GB ollama model dump).
docker volume rm mkt-solution_ollamadata
# SAFE: mkt-solution compose project is retired; postgres data, not referenced anywhere.
docker volume rm mkt-solution_pgdata
# SAFE: mkt-solution compose project is retired; qdrant vectors — active qdrant uses `qdrant-data`.
docker volume rm mkt-solution_qdrantdata
# SAFE: mkt-solution compose project is retired; grafana dashboards duplicate of ai-folder_grafana-data.
docker volume rm mkt-solution_grafanadata
# SAFE: mkt-solution compose project is retired; prometheus TSDB duplicate of ai-folder_prometheus-data.
docker volume rm mkt-solution_prometheusdata
# SAFE: mkt-solution compose project is retired; redis data duplicate of redis-data.
docker volume rm mkt-solution_redisdata

# SAFE: mkt-stack compose project is retired; no running container references any mkt-stack_* volume.
docker volume rm mkt-stack_grafana_data mkt-stack_postgres_data mkt-stack_redisinsight_data mkt-stack_prometheus_data mkt-stack_pgadmin_data mkt-stack_minio_data mkt-stack_redis_data mkt-stack_mailpit_data

# SAFE: ai-lab compose project is retired; gitlab/ollama/qdrant/loki/prom/grafana duplicates of ai-folder_* and top-level volumes.
docker volume rm ai-lab_gitlab_logs ai-lab_prometheus_data ai-lab_gitlab_data ai-lab_loki_data ai-lab_dind_data ai-lab_grafana_data ai-lab_gitlab_config ai-lab_gitlab_runner_config ai-lab_ollama_data ai-lab_qdrant_data

# SAFE: brandmatik-infra was the "self-hosted brandmatik gitlab + nexus" experiment, now dead; biggest reclaim is 6.904 GB of orphaned nexus data.
docker volume rm brandmatik-infra_nexus-data brandmatik-infra_gitlab-logs brandmatik-infra_gitlab-data brandmatik-infra_gitlab-config

# SAFE: brandmatik no longer runs its own grafana/prometheus sidecars (it scrapes via the shared infra-stack observability).
docker volume rm brandmatik_brandmatik-grafana brandmatik_brandmatik-prometheus

# SAFE: prod-stack compose is no longer deployed on this host; volumes carry com.docker.compose.project=prod-stack. Data lives in infra-stack equivalents.
docker volume rm \
  prod-splunk-var prod-splunk-etc prod-open-webui-data prod-trivy-cache prod-gitlab-data \
  prod-gitlab-logs prod-sonarqube-data prod-jenkins-data prod-sonarqube-db-data prod-redmine-db-data \
  prod-grafana-data prod-postgres-data prod-prometheus-data prod-loki-data \
  prod-jenkins-agent-1-data prod-jenkins-agent-2-data prod-jenkins-agent-3-data \
  prod-nexus-data prod-gitea-data prod-gitlab-config prod-sonarqube-logs prod-minio-data \
  prod-redmine-themes prod-sonarqube-extensions prod-ollama-data prod-redis-data \
  prod-redmine-plugins prod-gitlab-runner-config prod-redmine-data prod-gitea-runner-data \
  prod-devops-tools-config prod-chromadb-data

# SAFE: current taskflow compose declares no volumes (gateway + auth + task + notification + mailhog only); these are leftovers from an older richer compose.
docker volume rm taskflow_postgres_data taskflow_prometheus_data taskflow_grafana_data taskflow_redis_data

# SAFE: Gitea Actions per-job caches from two long-completed CI tasks (359, 361); new jobs create fresh volumes.
docker volume rm \
  GITEA-ACTIONS-TASK-359_WORKFLOW-CI-CD-Pipeline_JOB-compile \
  GITEA-ACTIONS-TASK-361_WORKFLOW-CI-CD-Pipeline_JOB-compile \
  GITEA-ACTIONS-TASK-359_WORKFLOW-CI-CD-Pipeline_JOB-compile-env \
  GITEA-ACTIONS-TASK-361_WORKFLOW-CI-CD-Pipeline_JOB-compile-env

# SAFE: stale "workspace" volumes from an earlier agent compose — active agents use clawd_jenkins-agent-{1,2,3}-data (different naming).
docker volume rm clawd_jenkins-agent1-workspace clawd_jenkins-agent2-workspace

# SAFE: superseded by sonarqube-* (the active SonarQube storage).
docker volume rm sonar-data sonar-logs sonar-extensions

# SAFE: single-word duplicates of the active ai-folder_* + ollama volumes (see duplicate-risk table).
docker volume rm ollama-data grafana-data prometheus-data loki-data

# SAFE: empty leftover configmap-style volumes from old compose iterations and never-populated caches.
docker volume rm devops-tools-config backend_devops-tools-config devops-tools-backend_devops-tools-config dev-stack_devops-tools-config infra-stack_vault-data act-toolcache maven-repo-cache
```

### Tier B — 500 GitLab Runner per-job caches (2.60 GB, zero risk)

```bash
# SAFE: every runner-*-cache-* volume is a per-pipeline cache created by gitlab-runner. They are regenerated automatically on the next job run.
# All 500 have LINKS=0 (not referenced by any container). Piping through xargs removes them in one shot.
docker volume ls --filter dangling=true --format '{{.Name}}' | grep '^runner-' | xargs -r docker volume rm
```

### Tier C — 172 dangling anonymous volumes (13.38 GB, low risk)

```bash
# SAFE: all 172 are dangling anonymous volumes (64-hex names) with no container reference (verified against `docker ps -a --filter volume=`).
# The 4 anonymous volumes that ARE held (2 vault-init, 2 Docker Desktop K8s) are EXCLUDED by the dangling filter — they will not be touched.
# Biggest reclaim in this tier: ed97c4a4... (6.075 GB) and 6ba17e26... (2.188 GB), both dated 2026-01-17.
docker volume ls --filter dangling=true --format '{{.Name}}' | grep -E '^[0-9a-f]{64}$' | xargs -r docker volume rm
```

### EXECUTE WITH

```bash
# Ordered execution (safest first, biggest reclaim per step):
# 1) Dry-run first: just preview what Tier B+C would touch:
docker volume ls --filter dangling=true --format '{{.Name}}' | grep -E '^(runner-|[0-9a-f]{64}$)' | wc -l   # should print 672 (500 runner + 172 anon)
# 2) Run Tier A (named), then Tier B (runner caches), then Tier C (anon) in that order.
# 3) After each tier, re-run `docker system df` to confirm reclaim before moving on.
# Combined reclaim after all three tiers: ~55.17 GB (39.19 named + 2.60 runner + 13.38 anon).
# The remaining ~1.55 GB of "orphan" space belongs to Docker Desktop's Kind K8s node — it's
# preserved intentionally (341bb1e... + de8e6608... are held by desktop-control-plane and kind-cloud-provider).
#
# Hard stop reminder: section 5 enumerates every volume that MUST survive this process.
# The commands above are scoped — they never name a preserve-list volume — but always eyeball
# the output of `docker volume ls` before running Tier C if you have added new tools since this audit.
```

---

## Appendix — verification commands used

```bash
# Context + counts (before pruning, baseline)
unset DOCKER_HOST; export DOCKER_CONTEXT=desktop-linux; export MSYS_NO_PATHCONV=1
docker volume ls | wc -l        # expect 810 incl. header
docker ps --format '{{.Names}}' | wc -l        # expect 73

# Per-container mount dump
for c in $(docker ps --format '{{.Names}}'); do
  docker inspect "$c" --format "$c"'|{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}::{{.Destination}}  {{end}}{{end}}'
done

# Dangling set (should be 758 before pruning)
docker volume ls --filter dangling=true --format '{{.Name}}' | wc -l

# Full size table (where sizes in section 1 come from)
docker system df -v | sed -n '/^Local Volumes space usage:/,/^Build cache/p'

# Compose-project labels on any suspect volume
docker volume inspect <name> --format '{{.CreatedAt}} | project={{index .Labels "com.docker.compose.project"}}'

# Find the container holding a "linked but not running" volume
docker volume rm --force <name>   # fails with the holding container ID if one exists
docker inspect <container-id> --format '{{.Name}} {{.State.Status}} {{.Config.Image}}'
```

## Rollback / mitigation

- This is a read-only audit; no volumes were touched. Nothing to roll back from the audit itself.
- Before the operator runs the Tier A/B/C commands, take an optional backup of anything you still care about:
  - `docker run --rm -v mkt-solution_ollamadata:/src -v "$PWD:/backup" alpine tar czf /backup/mkt-solution_ollamadata.tgz -C /src .`
  - Same pattern works for any orphan. Skip this for any volume in section 5 — those live on a running container and should be snapshotted with the app quiesced, not with a throwaway alpine tar.
- If a prune unexpectedly kills a tool: the tool's current ACTIVE volume is documented in section 1; recreate the container with the same named volume and it resumes. Only the section-5 bind mount for GitLab is irreplaceable without a Git/CI re-seed.
