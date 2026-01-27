# GitLab Runner DinD Configuration - Complete Setup

## What Was Configured

Your GitLab runner is now configured with **Docker-in-Docker (DinD)** capability for building and pushing Docker images to Nexus registry.

## Files Modified/Created

### 1. Runner Configuration
**[java-pipeline/runner-config.toml](java-pipeline/runner-config.toml)**
- Updated concurrent jobs from 1 to 3
- Added DinD service configuration with `docker:24-dind`
- Enabled Docker socket sharing (`/var/run/docker.sock`)
- Configured `modernization-network` for service communication
- Set 2GB shared memory for Docker operations

### 2. CI/CD Pipeline
**[java-pipeline/.gitlab-ci.yml](java-pipeline/.gitlab-ci.yml)**
- Enhanced Docker build job with DinD variables
- Added environment variables for Docker registry
- Configured DinD service with TLS disabled (for reliability)
- Added layer caching flags for faster builds

### 3. Setup Script (NEW)
**[files/setup-gitlab-runner-dind.ps1](files/setup-gitlab-runner-dind.ps1)**
- PowerShell script for automatic runner setup
- Creates runner configuration with DinD enabled
- Starts GitLab runner container
- Provides comprehensive setup guidance

### 4. Documentation (NEW)
**[files/RUNNER-SETUP.md](files/RUNNER-SETUP.md)**
- Complete runner setup guide
- Configuration explanations
- Troubleshooting section
- Security considerations
- Performance optimization tips

## Quick Setup Steps

### Step 1: Run the Setup Script
```powershell
cd files
.\setup-gitlab-runner-dind.ps1 -GitLabUrl "http://gitlab-server" -RunnerName "docker-dind-runner"
```

### Step 2: Configure GitLab CI/CD Variables
In GitLab UI (Settings > CI/CD > Variables):
- `DOCKER_REGISTRY_USER`: Your Nexus username
- `DOCKER_REGISTRY_PASSWORD`: Your Nexus password (mark as **Masked**)
- `DOCKER_REGISTRY`: `nexus-docker:5001`
- `DOCKER_IMAGE_NAME`: `java-app`

### Step 3: Verify Runner is Running
```powershell
docker logs -f gitlab-runner
```

## Key Configuration Points

### DinD Service Setup
```yaml
services:
  - name: docker:24-dind
    alias: docker
    command: ["--tls=false"]  # Reliability without TLS in dev
```

### Docker Socket Sharing
```toml
volumes = [
  "/cache",
  "/var/run/docker.sock:/var/run/docker.sock"  # Access host Docker
]
```

### Environment Variables
```yaml
DOCKER_TLS_CERTDIR: ""              # Required for DinD
DOCKER_HOST: tcp://docker:2375      # DinD endpoint
DOCKER_DRIVER: overlay2              # Efficient storage
FF_DOCKER_LAYER_CACHING: "true"     # Reuse build layers
```

## How It Works

```
1. GitLab CI/CD triggers docker_build job
   ↓
2. Job runs in docker:24-cli container
   ↓
3. DinD service (docker:24-dind) provides Docker daemon
   ↓
4. Job executes docker build/push commands
   ↓
5. Image gets pushed to nexus-docker:5001 registry
```

## Docker Build Commands in Your Pipeline

Example in `.gitlab-ci.yml`:
```yaml
script:
  - echo "$DOCKER_REGISTRY_PASSWORD" | docker login -u "$DOCKER_REGISTRY_USER" --password-stdin $DOCKER_REGISTRY
  - docker build -t $DOCKER_REGISTRY/$DOCKER_IMAGE_NAME:${CI_COMMIT_SHA:0:8} .
  - docker push $DOCKER_REGISTRY/$DOCKER_IMAGE_NAME:${CI_COMMIT_SHA:0:8}
```

## Networking

- All components use `modernization-network` bridge
- Service discovery by container name:
  - `docker:2375` → DinD daemon
  - `nexus-docker:5001` → Nexus registry
  - `gitlab-server` → GitLab instance

## Validation

Check runner status:
```bash
# View runner logs
docker logs gitlab-runner

# Test Docker connectivity
docker exec gitlab-runner docker ps

# List active jobs
docker exec gitlab-runner gitlab-runner --debug list
```

## Next Steps

1. Register runner with GitLab if not done automatically
2. Set CI/CD variables for Nexus authentication
3. Trigger a test pipeline to verify Docker build works
4. Monitor logs: `docker logs -f gitlab-runner`

## Troubleshooting Reference

See [files/RUNNER-SETUP.md](files/RUNNER-SETUP.md) for detailed troubleshooting:
- Runner connection issues
- Docker daemon connectivity
- Nexus registry authentication
- Disk space and memory issues

## Security Notes

✅ **Development**: Current setup is fine for local development
⚠️ **Production**: 
- Enable TLS for DinD
- Don't share docker.sock (use Kubernetes executor instead)
- Use proper registry authentication
- Rotate credentials regularly
- Add network policies

For production, consider Kubernetes executor with pod security policies.
