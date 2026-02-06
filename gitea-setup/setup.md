# Gitea Setup Guide

Free, self-hosted GitHub alternative with GitHub Actions-compatible runners.

## Quick Start

### 1. Start Gitea Server

```bash
cd d:/Repos/ai-folder/gitea-setup
docker-compose up -d gitea-server
```

### 2. Initial Setup

1. Open http://localhost:3002 in your browser
2. Complete the initial setup wizard:
   - Database: SQLite3 (default)
   - Site Title: "AI Pipeline Projects"
   - Admin Account: Create your admin user
3. Click "Install Gitea"

### 3. Create Access Token

1. Login with your admin account
2. Go to Settings > Applications > Generate New Token
3. Name: "devops-backend"
4. Select scopes: `repo`, `admin:org`, `write:packages`
5. Copy the token

### 4. Register Runner

Get the runner registration token:

```bash
# Login to Gitea as admin, then:
# Go to Site Administration > Actions > Runners > Create new Runner
# Copy the registration token
```

Set the token and start runner:

```bash
export GITEA_RUNNER_TOKEN=<your-registration-token>
docker-compose up -d gitea-runner
```

### 5. Configure Backend

Update the devops-tools-backend environment:

```bash
# In devops-tools-backend docker-compose.yml or .env
GITHUB_URL=http://gitea-server:3000
GITHUB_TOKEN=<your-access-token>
```

Restart the backend:

```bash
cd d:/Repos/ai-folder/devops-tools-backend
docker-compose up -d devops-tools-backend
```

## Repository Setup

### Create Test Repository

1. In Gitea, click "+ New Repository"
2. Name: "java-test-project"
3. Initialize with README

### Configure Repository Secrets

For the workflow to access Nexus and other services:

1. Go to Repository > Settings > Actions > Secrets
2. Add these secrets:

| Secret | Value |
|--------|-------|
| `NEXUS_REGISTRY` | `localhost:5001` |
| `NEXUS_INTERNAL_REGISTRY` | `ai-nexus:5001` |
| `NEXUS_USERNAME` | `admin` |
| `NEXUS_PASSWORD` | `<your-nexus-password>` |
| `SONARQUBE_URL` | `http://ai-sonarqube:9000` |
| `SONAR_TOKEN` | `<your-sonar-token>` |
| `SPLUNK_HEC_URL` | `http://ai-splunk:8088` |
| `SPLUNK_HEC_TOKEN` | `<your-splunk-token>` |
| `DEVOPS_BACKEND_URL` | `http://devops-tools-backend:8003` |

## Generate Pipeline

Use the backend API to generate a workflow:

```bash
curl -X POST "http://localhost:8003/api/v1/github-pipeline/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "http://gitea-server:3000/your-user/java-test-project",
    "github_token": "<your-gitea-token>"
  }'
```

## Verify Setup

Check runner status:

```bash
docker logs gitea-runner
```

Check Gitea Actions in repository:
- Go to Repository > Actions
- You should see workflow runs after pushing to a branch

## Troubleshooting

### Runner Not Connecting

```bash
# Check runner logs
docker logs gitea-runner

# Verify network connectivity
docker exec gitea-runner curl -s http://gitea-server:3000/api/healthz
```

### Actions Not Running

1. Ensure Actions are enabled in Gitea:
   - Site Administration > Configuration > Actions
   - Check "Enable Actions"

2. Verify runner is registered:
   - Site Administration > Actions > Runners
   - Runner should show as "Online"

### Docker-in-Docker Issues

If builds fail with Docker errors:

```bash
# Ensure Docker socket is mounted
docker exec gitea-runner ls -la /var/run/docker.sock

# Check Docker access
docker exec gitea-runner docker ps
```

## Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ai-platform-net                          │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ gitea-server │    │ gitea-runner │    │ devops-tools │      │
│  │   :3000      │◄──►│   (actions)  │    │   :8003      │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  ai-nexus    │    │ ai-sonarqube │    │   chromadb   │      │
│  │   :5001      │    │    :9000     │    │    :8000     │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Comparison with GitHub Actions

| Feature | GitHub Actions | Gitea Actions |
|---------|----------------|---------------|
| Workflow Syntax | YAML | YAML (compatible) |
| Runner | GitHub-hosted / Self-hosted | Self-hosted |
| Secrets | Repository Secrets | Repository Secrets |
| Artifacts | actions/upload-artifact | actions/upload-artifact |
| Docker | docker/build-push-action | docker/build-push-action |
| Cost | Free tier limits | Free (self-hosted) |

## Files

- `docker-compose.yml` - Gitea server and runner
- `runner-config.yaml` - Runner configuration
- `setup.md` - This guide
