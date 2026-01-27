# GitLab Runner with Docker-in-Docker (DinD) Setup

Complete guide for configuring a GitLab runner capable of building and pushing Docker images to Nexus registry.

## Quick Start

```powershell
cd files
.\setup-gitlab-runner-dind.ps1 -GitLabUrl "http://gitlab-server" -RunnerName "docker-dind-runner"
```

The script will:
1. Verify Docker is running
2. Create the `modernization-network` bridge (if needed)
3. Generate runner configuration with DinD support
4. Optionally start the runner container

## Architecture

```
GitLab CI/CD Pipeline (.gitlab-ci.yml)
        ↓
  docker_build job
        ↓
Runner (docker executor)
        ↓
DinD Service (docker:24-dind)
        ↓
Docker Socket Sharing (/var/run/docker.sock)
        ↓
Build & Push to Nexus Registry
```

## Configuration Details

### Runner Configuration (`runner-config.toml`)

Key settings for Docker-in-Docker:

```toml
[[runners]]
  name = "docker-dind-runner"
  executor = "docker"
  
  [runners.docker]
    image = "docker:24-cli"           # Lightweight Docker client
    privileged = true                 # Required for Docker operations
    volumes = [
      "/cache",
      "/var/run/docker.sock:/var/run/docker.sock"  # Access host Docker daemon
    ]
    shm_size = 2147483648            # 2GB for builds
    network_mode = "modernization-network"
    
    [[runners.docker.services]]
      name = "docker:24-dind"         # Docker-in-Docker service
      alias = "docker"
      command = ["--tls=false"]       # Disable TLS for reliability
```

### CI/CD Pipeline Configuration

In your `.gitlab-ci.yml`:

```yaml
docker_build:
  stage: docker
  image: docker:24-cli
  services:
    - name: docker:24-dind
      alias: docker
      command: ["--tls=false"]
  
  variables:
    DOCKER_TLS_CERTDIR: ""             # Required for DinD
    DOCKER_HOST: tcp://docker:2375     # DinD endpoint
    DOCKER_DRIVER: overlay2
    FF_NETWORK_PER_BUILD: "true"       # Per-build network isolation
    FF_DOCKER_LAYER_CACHING: "true"    # Cache Docker layers
    DOCKER_REGISTRY: nexus-docker:5001
    DOCKER_IMAGE_NAME: java-app
  
  before_script:
    - sleep 5                          # Wait for DinD service
    - docker info                      # Verify connectivity
    - docker login -u $DOCKER_REGISTRY_USER -p $DOCKER_REGISTRY_PASSWORD $DOCKER_REGISTRY
  
  script:
    - docker build -t $DOCKER_REGISTRY/$DOCKER_IMAGE_NAME:latest .
    - docker push $DOCKER_REGISTRY/$DOCKER_IMAGE_NAME:latest
```

## Manual Runner Registration

If you prefer manual setup instead of the PowerShell script:

### 1. Create Configuration File

Create `~/.gitlab-runner/config.toml`:

```toml
concurrent = 3
check_interval = 0

[session_server]
  session_timeout = 1800

[[runners]]
  name = "docker-dind-runner"
  url = "http://gitlab-server"
  token = "YOUR_REGISTRATION_TOKEN"
  executor = "docker"
  
  [runners.docker]
    image = "docker:24-cli"
    privileged = true
    volumes = ["/cache", "/var/run/docker.sock:/var/run/docker.sock"]
    shm_size = 2147483648
    network_mode = "modernization-network"
    
    [[runners.docker.services]]
      name = "docker:24-dind"
      alias = "docker"
      command = ["--tls=false"]
```

### 2. Run the Runner Container

```bash
docker run -d \
  --name gitlab-runner \
  --restart unless-stopped \
  --network modernization-network \
  -v ~/.gitlab-runner/config.toml:/etc/gitlab-runner/config.toml:ro \
  -v /var/run/docker.sock:/var/run/docker.sock \
  gitlab/gitlab-runner:latest
```

### 3. Verify the Runner is Running

```bash
docker logs -f gitlab-runner
```

## GitLab CI/CD Variables Setup

Set these in GitLab (Settings > CI/CD > Variables):

| Variable | Value | Masked |
|----------|-------|--------|
| `DOCKER_REGISTRY_USER` | Nexus username | No |
| `DOCKER_REGISTRY_PASSWORD` | Nexus password | **Yes** |
| `DOCKER_REGISTRY` | `nexus-docker:5001` | No |
| `DOCKER_IMAGE_NAME` | `java-app` | No |

## Network Configuration

The runner must be on the same Docker network as Nexus:

```bash
# Verify network exists
docker network ls | grep modernization-network

# Create if missing
docker network create modernization-network
```

All services communicate by container name:
- `nexus-docker:5001` → Nexus Docker registry
- `docker:2375` → DinD service endpoint

## Troubleshooting

### Runner Won't Connect to GitLab

```bash
# Check runner logs
docker logs gitlab-runner

# Verify GitLab is reachable
docker exec gitlab-runner ping gitlab-server

# Test from runner container
docker run --rm --network modernization-network curlimages/curl curl http://gitlab-server
```

### Docker Commands Fail in Pipeline

```bash
# Check DinD service connectivity
docker exec gitlab-runner docker info

# Verify socket binding
docker inspect gitlab-runner | grep -A 10 Mounts
```

### Image Push Fails to Nexus

```bash
# Verify Nexus is accessible
docker run --rm --network modernization-network curlimages/curl curl http://nexus-docker:5001/v2/

# Check registry credentials in pipeline logs
# (ensure DOCKER_REGISTRY_PASSWORD is masked in CI/CD variables)

# Test login locally
docker login -u admin -p admin123 nexus-docker:5001
```

### Out of Disk Space During Builds

The `shm_size = 2147483648` (2GB) might need adjustment:
- Increase for large Docker image builds
- Decrease if system RAM is limited

Update in `runner-config.toml` and restart runner:

```bash
docker restart gitlab-runner
```

## Maintenance

### View Active Jobs

```bash
docker exec gitlab-runner gitlab-runner --debug list
```

### Update Runner Version

```bash
docker pull gitlab/gitlab-runner:latest
docker restart gitlab-runner
```

### Rotate Runner Token

1. In GitLab: Settings > CI/CD > Runners > Click runner > Rotate token
2. Update `runner-config.toml` with new token
3. Restart runner: `docker restart gitlab-runner`

## Performance Tips

1. **Cache Docker Layers**: Enable `FF_DOCKER_LAYER_CACHING` to reuse build layers
2. **Parallel Builds**: Set `concurrent = 3` (or higher) for multiple simultaneous jobs
3. **Shared Memory**: Increase `shm_size` if experiencing OOM errors
4. **Network**: Use `network_mode = "modernization-network"` for service communication

## Security Considerations

⚠️ **Production Deployment**:
- Use TLS with proper certificates (set `tls_verify = true`)
- Don't share `/var/run/docker.sock` in production (security risk)
- Use dedicated runner host with proper isolation
- Rotate credentials regularly
- Use masked CI/CD variables for secrets
- Restrict runner to specific projects/tags

For production, consider using Kubernetes executor with isolated pod security policies instead of Docker executor.

## References

- [GitLab Runner Documentation](https://docs.gitlab.com/runner/)
- [Docker-in-Docker Executor](https://docs.gitlab.com/runner/executors/docker.html#docker-in-docker)
- [Docker Service Variables](https://docs.gitlab.com/ee/ci/services/)
- [Nexus Docker Repository](https://help.sonatype.com/repomanager3/formats/docker-registry)
