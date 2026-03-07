# Dev-Stack Credentials Report

**Generated**: 2026-02-27
**Stack**: dev-stack (Docker Compose)
**Proxy**: nginx-proxy at `localhost:8443`
**Public URL**: `https://devstack.deepaksharma.live` (requires DNS CNAME setup)

> **WARNING**: This file contains sensitive credentials. Do NOT commit to public repositories.

---

## Quick Reference — Service URLs

| Service               | Local URL                              | Proxy Path              | Status  |
|-----------------------|----------------------------------------|-------------------------|---------|
| Dashboard             | http://localhost:8443/                 | `/`                     | UP      |
| DevOps Backend API    | http://localhost:8003                  | `/devops-api/`          | UP      |
| Ollama LLM            | http://localhost:11434                 | `/ollama/`              | UP      |
| ChromaDB              | http://localhost:8005                  | `/chromadb/`            | UP      |
| ChromaDB Admin        | http://localhost:3001                  | `/chromadb-admin/`      | UP      |
| GitLab                | http://localhost:8929                  | `/gitlab/`              | UP      |
| Gitea                 | http://localhost:3002                  | `/gitea/`               | UP      |
| Jenkins               | http://localhost:8080                  | `/jenkins/`             | UP      |
| SonarQube             | http://localhost:9002                  | `/sonarqube/`           | UP      |
| Nexus Repository      | http://localhost:8181                  | `/nexus/`               | UP      |
| Nexus Docker Registry | http://localhost:5001                  | —                       | UP      |
| Trivy Scanner         | http://localhost:8183                  | `/trivy/`               | UP      |
| Grafana               | http://localhost:3000                  | `/grafana/`             | UP      |
| Prometheus            | http://localhost:9090                  | `/prometheus/`          | UP      |
| Loki                  | http://localhost:3100                  | `/loki/`                | UP      |
| Jaeger                | http://localhost:16686                 | `/jaeger/`              | UP      |
| Splunk                | http://localhost:10000                 | `/splunk/`              | UP      |
| cAdvisor              | http://localhost:8182                  | `/cadvisor/`            | UP      |
| Node Exporter         | http://localhost:9100                  | `/node-exporter/`       | UP      |
| Vault                 | http://localhost:8200                  | `/vault/`               | UP      |
| MinIO Console         | http://localhost:9001                  | `/minio/`               | UP      |
| MinIO S3 API          | http://localhost:9000                  | `/s3/`                  | UP      |
| Jira                  | http://localhost:8180                  | `/jira/`                | UP      |
| Redmine               | http://localhost:8090                  | `/redmine/`             | UP      |

---

## 1. Source Control

### GitLab
| Field              | Value                                                          |
|--------------------|----------------------------------------------------------------|
| **URL**            | http://localhost:8929/gitlab/ or proxy `/gitlab/`              |
| **Admin User**     | `root`                                                         |
| **Admin Password** | `OHphO3nIQxoSOA5nuxITXal6OdSbTnLevUg5LZKGJSs=`               |
| **Admin PAT**      | `glpat-wKUolOvRfNgBP0jo1xgLUm86MQp1OjEH.01.0w08ce9g0`        |
| **Vault PAT**      | `glpat-fC1pn11xA-CrENmkqfY7bG86MQp1OjEH.01.0w04srs1r` (old, may be expired) |
| **SSH Port**       | `2224`                                                         |
| **Vault Path**     | `secret/gitlab`                                                |

**Service Account:**
| Field          | Value                                                      |
|----------------|-------------------------------------------------------------|
| **Username**   | `svc-devops-backend`                                        |
| **PAT**        | `glpat-q2PgrM5d_gMUU9cNeKnYcm86MQp1OjMH.01.0w00z8aj1`     |
| **Vault Path** | `secret/service-accounts/gitlab`                            |

### Gitea
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:3002 or proxy `/gitea/`        |
| **Admin User**     | `admin`                                         |
| **Admin Password** | `admin123`                                      |
| **API Token**      | `dbfd7723057682c2ce99a0fc5177f9f7660d68f6`      |
| **SSH Port**       | `2222`                                          |
| **Vault Path**     | `secret/gitea`                                  |
| **Orgs**           | `jenkins-projects`, `github-projects`           |

**Git Clone (SSH):** `ssh://git@localhost:2222/<org>/<repo>.git`
**Git Clone (HTTP):** `http://localhost:3002/<org>/<repo>.git`

---

## 2. CI/CD

### Jenkins
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:8080/jenkins/ or proxy `/jenkins/` |
| **Admin User**     | `admin`                                         |
| **Admin Password** | `admin123`                                      |
| **Git Token**      | `dbfd7723057682c2ce99a0fc5177f9f7660d68f6` (Gitea) |
| **Agent Label**    | `docker`                                        |
| **Agents**         | jenkins-agent-1, jenkins-agent-2, jenkins-agent-3 |
| **JNLP Port**      | `50000`                                         |
| **Vault Path**     | `secret/jenkins`                                |

**Service Account:**
| Field          | Value                    |
|----------------|--------------------------|
| **Username**   | `svc-devops-backend`     |
| **Password**   | `SvcD3v0ps2026`          |
| **Vault Path** | `secret/service-accounts/jenkins` |

---

## 3. Quality & Security

### SonarQube
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:9002 or proxy `/sonarqube/`    |
| **Admin User**     | `admin`                                         |
| **Admin Password** | `N7@qL9!fR2#XwA8$`                             |
| **Vault Path**     | `secret/sonarqube`                              |

**Database:**
| Field          | Value           |
|----------------|-----------------|
| **Host**       | `ai-sonar-db`   |
| **Port**       | `5432`          |
| **Database**   | `sonarqube`     |
| **User**       | `sonar`         |
| **Password**   | `sonarpass`     |

### Nexus Repository Manager
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:8181 or proxy `/nexus/`        |
| **Admin User**     | `admin`                                         |
| **Admin Password** | `r`                                             |
| **Docker Registry**| `localhost:5001`                                |
| **Vault Path**     | `secret/nexus`                                  |

**Service Account:**
| Field          | Value                    |
|----------------|--------------------------|
| **Username**   | `svc-devops-backend`     |
| **Password**   | `SvcD3v0ps2026`          |
| **Vault Path** | `secret/service-accounts/nexus` |

**Docker Login:**
```bash
docker login localhost:5001 -u admin -p r
```

### Trivy Scanner
| Field    | Value                                          |
|----------|-------------------------------------------------|
| **URL**  | http://localhost:8183 or proxy `/trivy/`        |
| **Auth** | None (API only)                                 |

---

## 4. Monitoring & Observability

### Grafana
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:3000/grafana/ or proxy `/grafana/` |
| **Admin User**     | `admin`                                         |
| **Admin Password** | `admin`                                         |

### Prometheus
| Field    | Value                                               |
|----------|------------------------------------------------------|
| **URL**  | http://localhost:9090/prometheus/ or proxy `/prometheus/` |
| **Auth** | None                                                 |

### Loki
| Field    | Value                                          |
|----------|-------------------------------------------------|
| **URL**  | http://localhost:3100 or proxy `/loki/`         |
| **Auth** | None (API only)                                 |

### Jaeger
| Field           | Value                                          |
|-----------------|-------------------------------------------------|
| **UI URL**      | http://localhost:16686 or proxy `/jaeger/`      |
| **Collector**   | `localhost:14268`                               |
| **Auth**        | None                                            |

### Splunk
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:10000 or proxy `/splunk/`      |
| **Admin User**     | `admin`                                         |
| **Admin Password** | `Admin@1234`                                    |
| **HEC Port**       | `8088`                                          |
| **Vault Path**     | `secret/splunk` (token empty — populate manually) |

### cAdvisor
| Field    | Value                                          |
|----------|-------------------------------------------------|
| **URL**  | http://localhost:8182 or proxy `/cadvisor/`     |
| **Auth** | None                                            |

### Node Exporter
| Field    | Value                                               |
|----------|------------------------------------------------------|
| **URL**  | http://localhost:9100 or proxy `/node-exporter/`     |
| **Auth** | None (metrics only)                                  |

---

## 5. AI & ML

### Ollama
| Field    | Value                                          |
|----------|-------------------------------------------------|
| **URL**  | http://localhost:11434 or proxy `/ollama/`      |
| **Auth** | None                                            |
| **Model**| `pipeline-generator-v5` (qwen3:32b)            |

### ChromaDB
| Field    | Value                                          |
|----------|-------------------------------------------------|
| **URL**  | http://localhost:8005 or proxy `/chromadb/`     |
| **Auth** | None                                            |

### ChromaDB Admin
| Field    | Value                                          |
|----------|-------------------------------------------------|
| **URL**  | http://localhost:3001 or proxy `/chromadb-admin/` |
| **Auth** | None                                            |

### DevOps Tools Backend (FastAPI)
| Field    | Value                                          |
|----------|-------------------------------------------------|
| **URL**  | http://localhost:8003 or proxy `/devops-api/`   |
| **Docs** | http://localhost:8003/docs                      |
| **Auth** | None (internal API)                             |

---

## 6. Storage & Secrets

### HashiCorp Vault
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:8200 or proxy `/vault/`        |
| **UI**             | http://localhost:8200/ui                        |
| **Root Token**     | `VAULT_TOKEN_REDACTED`                |
| **Auth Method**    | Token                                           |
| **Storage**        | File backend (persistent volume)                |
| **Auto-Unseal**    | Yes (vault-unseal sidecar)                      |

**Vault Secret Paths:**
| Path                             | Contents                  |
|----------------------------------|---------------------------|
| `secret/gitlab`                  | root username, password, token |
| `secret/gitea`                   | admin username, password, token |
| `secret/sonarqube`               | admin password, token     |
| `secret/nexus`                   | admin username, password  |
| `secret/jenkins`                 | admin username, password, git_token |
| `secret/splunk`                  | token (empty)             |
| `secret/jira`                    | username, api_token (empty) |
| `secret/openai`                  | (if configured)           |
| `secret/terraform`               | (if configured)           |
| `secret/service-accounts/gitlab` | svc-devops-backend token  |
| `secret/service-accounts/nexus`  | svc-devops-backend creds  |
| `secret/service-accounts/jenkins`| svc-devops-backend creds  |

### MinIO (S3-Compatible Storage)
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **Console URL**    | http://localhost:9001 or proxy `/minio/`        |
| **S3 API URL**     | http://localhost:9000 or proxy `/s3/`           |
| **Root User**      | `admin`                                         |
| **Root Password**  | `admin123`                                      |

**AWS CLI Configuration:**
```bash
aws configure --profile devstack-minio
# Access Key: admin
# Secret Key: admin123
# Region: us-east-1
# Endpoint: http://localhost:9000
```

---

## 7. Databases

### PostgreSQL (Main — Platform)
| Field          | Value                    |
|----------------|--------------------------|
| **Host**       | `localhost`              |
| **Port**       | `5432`                   |
| **Database**   | `modernization_platform` |
| **User**       | `platform`               |
| **Password**   | `platform123`            |
| **Container**  | `ai-postgres`            |

**Connection String:**
```
postgresql://platform:platform123@localhost:5432/modernization_platform
```

### PostgreSQL (SonarQube)
| Field          | Value           |
|----------------|-----------------|
| **Host**       | `ai-sonar-db` (internal only) |
| **Port**       | `5432`          |
| **Database**   | `sonarqube`     |
| **User**       | `sonar`         |
| **Password**   | `sonarpass`     |

### PostgreSQL (Jira)
| Field          | Value           |
|----------------|-----------------|
| **Host**       | `localhost` (internal: `jira-postgres`) |
| **Port**       | Internal only   |
| **Database**   | `jiradb`        |
| **User**       | `jira`          |
| **Password**   | `jira123`       |

### PostgreSQL (Redmine)
| Field          | Value           |
|----------------|-----------------|
| **Host**       | `redmine-db` (internal only) |
| **Port**       | `5432`          |
| **Database**   | `redmine`       |
| **User**       | `redmine`       |
| **Password**   | `redmine123`    |

### Redis
| Field          | Value           |
|----------------|-----------------|
| **Host**       | `localhost`     |
| **Port**       | `6379`          |
| **Password**   | None            |
| **Container**  | `redis`         |

**Connection String:**
```
redis://localhost:6379
```

---

## 8. Project Management

### Jira
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:8180 or proxy `/jira/`         |
| **Auth**           | Setup required (first-run wizard)               |
| **Vault Path**     | `secret/jira` (empty — populate after setup)    |

### Redmine
| Field              | Value                                          |
|--------------------|-------------------------------------------------|
| **URL**            | http://localhost:8090 or proxy `/redmine/`      |
| **Admin User**     | `admin`                                         |
| **Admin Password** | `admin` (default, change on first login)        |

---

## 9. Container Networks

| Network             | Purpose                             | Services                                              |
|----------------------|-------------------------------------|-------------------------------------------------------|
| `ai-platform-net`   | Core AI platform services           | backend, nginx, ollama, chromadb, postgres, redis, minio, vault, etc. |
| `gitlab-net`        | GitLab ecosystem                    | gitlab-server, gitlab-runner                          |
| `jenkins-net`       | Jenkins ecosystem                   | jenkins-master, jenkins-agents, gitea-server          |
| `monitoring-network`| Monitoring stack                    | grafana, prometheus, loki, jaeger, splunk, etc.       |
| `ticketing-net`     | Project management tools            | jira, jira-postgres, redmine, redmine-db              |

---

## 10. Docker Compose Management

**Start all services:**
```bash
docker-compose -p dev-stack -f "D:/Repos/ai-folder/dev-stack/infrastructure/docker-compose.yml" up -d
```

**Stop all services:**
```bash
docker-compose -p dev-stack -f "D:/Repos/ai-folder/dev-stack/infrastructure/docker-compose.yml" down
```

**View logs:**
```bash
docker-compose -p dev-stack -f "D:/Repos/ai-folder/dev-stack/infrastructure/docker-compose.yml" logs -f <service-name>
```

**Restart a single service:**
```bash
docker-compose -p dev-stack -f "D:/Repos/ai-folder/dev-stack/infrastructure/docker-compose.yml" restart <service-name>
```

---

## 11. Notes

- **GitLab** takes 3-5 minutes on cold start. Backend depends on it.
- **Vault** auto-unseals via `vault-unseal` sidecar container.
- **Vault root token** is stored at `/vault/file/.root-token` inside the vault container.
- **Nexus Docker registry** (`localhost:5001`) is used by CI/CD pipelines for pushing/pulling images.
- **Splunk token** and **Jira API token** are empty in Vault — populate manually after setup.
- **chromadb-admin** is an ARM image running on AMD64 — may restart frequently.
- **Port remappings** (due to Brandmatik conflicts): Nexus 8081->8181, Trivy 8083->8183, cAdvisor 8082->8182.
- **DNS setup needed**: Create CNAME record `devstack.deepaksharma.live` -> `deepak-desktop.tailac51e7.ts.net`.
