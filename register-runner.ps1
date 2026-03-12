# Script to register GitLab runner with proper tags
# This creates a valid runner config with the 'docker' tag

$configPath = "gitlab-runner\config\config\config.toml"
$tempConfig = @"
concurrent = 3
check_interval = 0
shutdown_timeout = 0

[session_server]
  session_timeout = 1800

[[runners]]
  name = "docker-dind-runner"
  url = "http://gitlab-server"
  token = "glrtr-test-token-placeholder"
  executor = "docker"
  clone_url = "http://gitlab-server"
  shell = "sh"
  tags = ["docker"]

  [runners.custom_build_dir]
    enabled = false

  [runners.cache]
    [runners.cache.s3]
    [runners.cache.gcs]
    [runners.cache.azure]

  [runners.docker]
    tls_verify = false
    image = "docker:24-cli"
    privileged = true
    disable_entrypoint_overwrite = false
    oom_kill_disable = false
    disable_cache = false
    volumes = ["/cache", "/var/run/docker.sock:/var/run/docker.sock"]
    shm_size = 2147483648
    network_mode = "modernization-network"

    [[runners.docker.services]]
      name = "docker:24-dind"
      alias = "docker"
      command = ["--tls=false"]

    [runners.docker.services.extra_hosts]
      "docker" = "127.0.0.1"
      "nexus-docker" = "127.0.0.1"

    [[runners.docker.services]]
      name = "postgres:15-alpine"
      alias = "postgres"

    [[runners.docker.services]]
      name = "redis:7-alpine"
      alias = "redis"

    [[runners.docker.services]]
      name = "minio/minio:latest"
      alias = "minio"

    [runners.docker.services.variables]
      MINIO_ROOT_USER = "minioadmin"
      MINIO_ROOT_PASSWORD = "minioadmin123"
"@

# Copy config to the runner container
Write-Host "Registering runner with docker tag..."
$tempConfig | Out-File -FilePath $configPath -Encoding UTF8 -Force

# Copy to Docker container
docker cp $configPath gitlab-runner:/etc/gitlab-runner/config.toml 2>$null

# Restart the runner
Write-Host "Restarting GitLab runner..."
docker restart gitlab-runner

Write-Host "Runner registered! It may take 10-30 seconds to appear in GitLab as active."
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Go to your project Settings > CI/CD > Runners"
Write-Host "2. Look for 'docker-dind-runner' with 'docker' tag"
Write-Host "3. If still showing offline, update the token in GitLab web UI"
