# Credentials & Integration Guide

This document describes all credentials and secrets required for the DevOps Tools Backend system.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CREDENTIALS ARCHITECTURE                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐
│  Backend Service    │ ◄── .env file (runtime secrets)
│  (devops-tools-     │
│   backend)          │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         GitLab CI/CD Variables                           │
│  (Per-project settings: Settings → CI/CD → Variables)                    │
│                                                                          │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐               │
│  │ NEXUS_USERNAME │ │ NEXUS_PASSWORD │ │  SONAR_TOKEN   │               │
│  │    (visible)   │ │   (masked)     │ │   (masked)     │               │
│  └────────────────┘ └────────────────┘ └────────────────┘               │
│                                                                          │
│  ┌────────────────┐ ┌────────────────┐                                  │
│  │SPLUNK_HEC_TOKEN│ │  GITLAB_TOKEN  │                                  │
│  │   (masked)     │ │   (masked)     │                                  │
│  └────────────────┘ └────────────────┘                                  │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      Pipeline Runtime (Jobs)                             │
│                                                                          │
│   compile ──► build ──► test ──► ... ──► notify ──► learn               │
│      │          │                           │          │                 │
│      │          │                           │          │                 │
│      ▼          ▼                           ▼          ▼                 │
│   (none)    Kaniko                      Splunk     Backend               │
│            Auth JSON                      HEC        API                 │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Backend Service Credentials (.env)

Location: `devops-tools-backend/.env`

### Required Variables

```bash
# =============================================================================
# GITLAB CONFIGURATION
# =============================================================================
# GitLab server URL (internal Docker network or external)
GITLAB_URL=http://gitlab-server

# GitLab Personal Access Token
# Scopes required: api, read_repository, write_repository
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxxx

# =============================================================================
# CHROMADB CONFIGURATION
# =============================================================================
# ChromaDB vector database URL
CHROMADB_URL=http://chromadb:8000

# =============================================================================
# OLLAMA CONFIGURATION
# =============================================================================
# Ollama LLM server URL
OLLAMA_URL=http://ollama:11434

# =============================================================================
# NEXUS CONFIGURATION
# =============================================================================
# Nexus Repository Manager URL
NEXUS_URL=http://ai-nexus:8081

# Nexus admin credentials (for health checks)
NEXUS_USERNAME=admin
NEXUS_PASSWORD=admin123

# =============================================================================
# SONARQUBE CONFIGURATION
# =============================================================================
# SonarQube server URL
SONARQUBE_URL=http://ai-sonarqube:9000

# SonarQube admin credentials
SONARQUBE_USERNAME=admin
SONARQUBE_PASSWORD=admin123

# =============================================================================
# SPLUNK CONFIGURATION (Optional)
# =============================================================================
# Splunk HTTP Event Collector URL
SPLUNK_HEC_URL=http://ai-splunk:8088

# =============================================================================
# DATABASE CONFIGURATION (Optional)
# =============================================================================
# PostgreSQL connection string
POSTGRES_URL=postgresql://user:pass@ai-postgres:5432/database

# Redis connection string
REDIS_URL=redis://redis:6379/0

# =============================================================================
# DEBUG MODE
# =============================================================================
DEBUG=true
```

### Security Notes

- **NEVER** commit `.env` file to version control
- Add `.env` to `.gitignore`
- Use Docker secrets in production
- Rotate tokens periodically

---

## 2. GitLab CI/CD Variables

Configure these in each GitLab project: **Settings → CI/CD → Variables**

### Required Variables

| Variable | Type | Protected | Masked | Description |
|----------|------|-----------|--------|-------------|
| `NEXUS_USERNAME` | Variable | No | No | Nexus registry username |
| `NEXUS_PASSWORD` | Variable | No | **Yes** | Nexus registry password |
| `SONAR_TOKEN` | Variable | No | **Yes** | SonarQube authentication token |
| `SPLUNK_HEC_TOKEN` | Variable | No | **Yes** | Splunk HEC token |
| `GITLAB_TOKEN` | Variable | No | **Yes** | GitLab API token (for RL) |

### Setting Variables via GitLab UI

1. Navigate to your project
2. Go to **Settings → CI/CD**
3. Expand **Variables** section
4. Click **Add variable**
5. Configure each variable:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Add Variable                                      │
├─────────────────────────────────────────────────────────────────────┤
│  Key:     NEXUS_PASSWORD                                            │
│  Value:   ********                                                  │
│                                                                     │
│  Type:    ○ Variable  ○ File                                        │
│                                                                     │
│  Environment scope: All (default)                                   │
│                                                                     │
│  Flags:                                                             │
│  [ ] Protect variable (only available on protected branches)        │
│  [✓] Mask variable (hide in job logs)                              │
│  [ ] Expand variable reference                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Setting Variables via API

```bash
# Add NEXUS_PASSWORD
curl -X POST "http://localhost:8929/api/v4/projects/9/variables" \
  -H "PRIVATE-TOKEN: glpat-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "NEXUS_PASSWORD",
    "value": "your-password",
    "masked": true,
    "protected": false
  }'

# Add SONAR_TOKEN
curl -X POST "http://localhost:8929/api/v4/projects/9/variables" \
  -H "PRIVATE-TOKEN: glpat-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "SONAR_TOKEN",
    "value": "squ_xxxxx",
    "masked": true,
    "protected": false
  }'
```

---

## 3. Nexus Registry Authentication

### Overview

The pipeline uses two registry endpoints:

| Variable | Value | Purpose |
|----------|-------|---------|
| `NEXUS_PULL_REGISTRY` | `localhost:5001` | Pull images for jobs (Docker Desktop) |
| `NEXUS_INTERNAL_REGISTRY` | `ai-nexus:5001` | Push images from Kaniko (container) |

### Kaniko Authentication

Kaniko builds Docker images inside the pipeline. It requires authentication:

```yaml
build_image:
  stage: build
  image:
    name: ${NEXUS_PULL_REGISTRY}/apm-repo/demo/kaniko-executor:debug
    entrypoint: [""]
  script:
    # Create Docker auth config
    - mkdir -p /kaniko/.docker
    - |
      echo "{\"auths\":{\"${NEXUS_INTERNAL_REGISTRY}\":{\"username\":\"${NEXUS_USERNAME}\",\"password\":\"${NEXUS_PASSWORD}\"}}}" > /kaniko/.docker/config.json
    # Build and push
    - /kaniko/executor \
        --context "${CI_PROJECT_DIR}" \
        --dockerfile "${CI_PROJECT_DIR}/Dockerfile" \
        --destination "${NEXUS_INTERNAL_REGISTRY}/apm-repo/demo/${IMAGE_NAME}:${IMAGE_TAG}" \
        --build-arg BASE_REGISTRY=${NEXUS_INTERNAL_REGISTRY} \
        --insecure \
        --skip-tls-verify \
        --insecure-registry=ai-nexus:5001
```

### Nexus Docker Repository Setup

1. Login to Nexus UI: `http://localhost:8081`
2. Create Docker hosted repository:
   - Name: `docker-hosted`
   - HTTP port: `5001`
   - Allow anonymous pull: Yes (for development)
3. Create Docker proxy (optional for Docker Hub):
   - Name: `docker-proxy`
   - Remote URL: `https://registry-1.docker.io`

---

## 4. SonarQube Token

### Creating a SonarQube Token

1. Login to SonarQube: `http://localhost:9000`
2. Go to **My Account → Security**
3. Generate token:
   - Name: `gitlab-ci`
   - Type: `Project Analysis Token`
   - Project: Select your project (or Global)
4. Copy the token: `squ_xxxxxxxxxxxxxxxxx`

### Using in Pipeline

```yaml
quality:
  stage: quality
  image: ${NEXUS_PULL_REGISTRY}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
  script:
    - sonar-scanner \
        -Dsonar.projectKey=${CI_PROJECT_NAME} \
        -Dsonar.host.url=${SONARQUBE_URL} \
        -Dsonar.token=${SONAR_TOKEN}
  allow_failure: true
```

---

## 5. Splunk HEC Token

### Creating HEC Token

1. Login to Splunk: `http://localhost:8000`
2. Go to **Settings → Data Inputs → HTTP Event Collector**
3. Click **New Token**:
   - Name: `gitlab-ci`
   - Source type: `_json`
   - Index: `main`
4. Copy the token

### Using in Pipeline

```yaml
notify_success:
  stage: notify
  image: ${NEXUS_PULL_REGISTRY}/apm-repo/demo/curlimages-curl:latest
  script:
    - |
      curl -k -X POST "${SPLUNK_HEC_URL}/services/collector/event" \
        -H "Authorization: Splunk ${SPLUNK_HEC_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"event": "Pipeline succeeded", "sourcetype": "gitlab-ci"}'
  when: on_success
  allow_failure: true
```

---

## 6. GitLab Personal Access Token

### Creating GitLab PAT

1. Login to GitLab: `http://localhost:8929`
2. Go to **User Settings → Access Tokens**
3. Create token:
   - Name: `devops-backend`
   - Expiration: Set appropriate date
   - Scopes:
     - [x] `api` - Full API access
     - [x] `read_repository` - Read repository
     - [x] `write_repository` - Write repository
4. Copy the token: `glpat-xxxxxxxxxxxxx`

### Required Scopes

| Scope | Purpose |
|-------|---------|
| `api` | Access GitLab API for project/pipeline info |
| `read_repository` | Read repository files for analysis |
| `write_repository` | Create branches and commits |

---

## 7. Security Best Practices

### Development Environment

```bash
# Use environment variables
export GITLAB_TOKEN=glpat-xxxxx
export NEXUS_PASSWORD=admin123

# Or use .env file (gitignored)
cp .env.example .env
# Edit .env with your values
```

### Production Environment

```yaml
# docker-compose.yml with Docker secrets
services:
  devops-tools-backend:
    secrets:
      - gitlab_token
      - nexus_password
    environment:
      GITLAB_TOKEN_FILE: /run/secrets/gitlab_token

secrets:
  gitlab_token:
    external: true
  nexus_password:
    external: true
```

### Kubernetes

```yaml
# Secret
apiVersion: v1
kind: Secret
metadata:
  name: devops-tools-secrets
type: Opaque
stringData:
  GITLAB_TOKEN: glpat-xxxxx
  NEXUS_PASSWORD: admin123

# Deployment
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: backend
          envFrom:
            - secretRef:
                name: devops-tools-secrets
```

---

## 8. Credential Rotation

### Recommended Schedule

| Credential | Rotation Frequency |
|------------|-------------------|
| GitLab Token | 90 days |
| Nexus Password | 180 days |
| SonarQube Token | 90 days |
| Splunk HEC Token | 365 days |

### Rotation Procedure

1. **Generate new credential** in the respective service
2. **Update backend `.env`** file
3. **Update GitLab CI/CD variables** for all projects
4. **Restart backend service**
5. **Verify pipeline execution**
6. **Revoke old credential** after verification

---

## 9. Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` from GitLab | Invalid/expired token | Regenerate PAT |
| `403 Forbidden` on push | Missing write_repository scope | Add scope to token |
| Kaniko auth failure | Wrong registry URL | Check NEXUS_INTERNAL_REGISTRY |
| SonarQube connection refused | Token not set | Add SONAR_TOKEN to CI/CD |
| Image pull failure | NEXUS_PULL_REGISTRY incorrect | Use localhost:5001 |

### Debugging Commands

```bash
# Test GitLab token
curl -H "PRIVATE-TOKEN: glpat-xxxxx" \
  "http://localhost:8929/api/v4/user"

# Test Nexus registry
curl -u admin:admin123 \
  "http://localhost:8081/service/rest/v1/status"

# Test SonarQube token
curl -u squ_xxxxx: \
  "http://localhost:9000/api/authentication/validate"

# Check GitLab CI variables
curl -H "PRIVATE-TOKEN: glpat-xxxxx" \
  "http://localhost:8929/api/v4/projects/9/variables"
```
