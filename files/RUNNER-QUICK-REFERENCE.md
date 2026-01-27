# GitLab Runner DinD - Quick Reference Card

## 📋 Files Modified/Created

| File | Change | Purpose |
|------|--------|---------|
| `java-pipeline/runner-config.toml` | ✏️ Modified | DinD runner config with socket sharing |
| `java-pipeline/.gitlab-ci.yml` | ✏️ Modified | Enhanced Docker build job variables |
| `files/setup-gitlab-runner-dind.ps1` | ✨ Created | Automated runner setup script |
| `files/RUNNER-SETUP.md` | ✨ Created | Complete setup guide & troubleshooting |
| `files/RUNNER-SETUP-SUMMARY.md` | ✨ Created | Configuration overview |
| `files/gitlab-ci-dind-example.yml` | ✨ Created | Complete pipeline example |

## 🚀 Quick Start

```powershell
# 1. Run setup script
cd files
.\setup-gitlab-runner-dind.ps1

# 2. Enter registration token when prompted (from GitLab)
# 3. Script will start the runner

# 4. Set CI/CD variables in GitLab UI
#    Settings > CI/CD > Variables:
#    - DOCKER_REGISTRY_USER (your Nexus username)
#    - DOCKER_REGISTRY_PASSWORD (masked)
```

## 🔑 Key Configuration

### DinD Service
```yaml
services:
  - name: docker:24-dind
    alias: docker
    command: ["--tls=false"]
```

### Environment Variables
```yaml
DOCKER_TLS_CERTDIR: ""              # Required for DinD
DOCKER_HOST: tcp://docker:2375      # DinD endpoint
DOCKER_DRIVER: overlay2              # Storage driver
```

### Runner Settings
```toml
privileged = true                    # Docker access
volumes = [
  "/var/run/docker.sock:/var/run/docker.sock"  # Socket sharing
]
shm_size = 2147483648               # 2GB shared memory
```

## ✅ Verification Steps

```bash
# 1. Check runner is running
docker ps | grep gitlab-runner

# 2. View logs
docker logs -f gitlab-runner

# 3. Test Docker in runner
docker exec gitlab-runner docker ps

# 4. Trigger test pipeline in GitLab
# Watch the docker_build job in GitLab UI
```

## 📝 GitLab CI/CD Variables Required

```
DOCKER_REGISTRY_USER       = <nexus-username>
DOCKER_REGISTRY_PASSWORD   = <nexus-password> [MASKED]
DOCKER_REGISTRY            = nexus-docker:5001
DOCKER_IMAGE_NAME          = java-app
```

## 🐳 How DinD Works

```
CI Pipeline
   ↓
Docker executor (docker:24-cli)
   ↓
DinD service (docker:24-dind) provides Docker daemon
   ↓
Runner can execute: docker build, docker push, etc.
   ↓
Images pushed to Nexus registry (5001)
```

## 🔧 Common Commands

```bash
# View runner logs
docker logs gitlab-runner

# Restart runner
docker restart gitlab-runner

# Check Docker daemon in runner
docker exec gitlab-runner docker info

# List active jobs
docker exec gitlab-runner gitlab-runner --debug list

# Rotate runner token (after updating in GitLab)
docker restart gitlab-runner
```

## ⚠️ Important Notes

1. **TLS Disabled**: Using `--tls=false` for development reliability
2. **Privileged Mode**: Required for Docker operations in CI
3. **Socket Sharing**: Allows accessing host Docker daemon
4. **Network**: Runner must be on `modernization-network`
5. **Credentials**: Always mask sensitive variables in GitLab

## 🚨 Troubleshooting Quick Links

- Runner won't connect: Check GitLab URL and token in config
- Docker commands fail: Verify `docker info` works in runner
- Image push fails: Check Nexus credentials and registry URL
- Out of memory: Increase `shm_size` in config

See `files/RUNNER-SETUP.md` for detailed troubleshooting.

## 📚 Full Documentation

- **Setup Guide**: `files/RUNNER-SETUP.md`
- **Configuration Summary**: `files/RUNNER-SETUP-SUMMARY.md`
- **Pipeline Example**: `files/gitlab-ci-dind-example.yml`
- **Runner Config**: `java-pipeline/runner-config.toml`
- **CI/CD Config**: `java-pipeline/.gitlab-ci.yml`

## 🎯 Next Steps

1. ✅ Run `setup-gitlab-runner-dind.ps1` to create/start runner
2. ✅ Get registration token from GitLab (Settings > CI/CD > Runners)
3. ✅ Set Docker registry credentials in GitLab variables
4. ✅ Push changes to trigger `docker_build` job
5. ✅ Verify images appear in Nexus registry
