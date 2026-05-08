<#
.SYNOPSIS
GitLab Runner setup with Docker-in-Docker (DinD) for building and pushing Docker images to Nexus

.DESCRIPTION
Registers a Docker executor runner with DinD capability for:
- Building Docker images within CI/CD pipeline
- Pushing images to Nexus Docker registry (port 5001)
- Sharing docker.sock for efficient builds
- Running on the modernization-network bridge

.PARAMETER GitLabUrl
GitLab server URL (default: http://gitlab-server)

.PARAMETER RunnerName
Name of the runner (default: docker-dind-runner)

.PARAMETER RunnerToken
Registration token from GitLab project (leave empty to use interactive registration)

.PARAMETER Concurrent
Number of concurrent jobs (default: 3)

.PARAMETER DockerRegistry
Nexus Docker registry URL (default: nexus-docker:5001)

.PARAMETER RegistryUser
Docker registry username (for .dockercfg credentials)

.PARAMETER RegistryPassword
Docker registry password (for .dockercfg credentials)

.EXAMPLE
# Interactive runner registration
.\setup-gitlab-runner-dind.ps1 -GitLabUrl "http://gitlab-server" -RunnerName "docker-dind-runner"

# With Nexus credentials
.\setup-gitlab-runner-dind.ps1 -GitLabUrl "http://gitlab-server" `
  -RegistryUser "nexus-user" -RegistryPassword "nexus-pass"

.NOTES
Requires:
- Docker and Docker Desktop running
- Access to GitLab server
- Runner registration token from GitLab (Settings > CI/CD > Runners)
#>

[CmdletBinding()]
param(
  [string]$GitLabUrl = "http://gitlab-server",
  [string]$RunnerName = "docker-dind-runner",
  [string]$RunnerToken = "",
  [int]$Concurrent = 3,
  [string]$DockerRegistry = "nexus-docker:5001",
  [string]$RegistryUser = "",
  [string]$RegistryPassword = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info($m) { Write-Host "[INFO ] $m" -ForegroundColor Cyan }
function Write-Warn($m) { Write-Host "[WARN ] $m" -ForegroundColor Yellow }
function Write-Success($m) { Write-Host "[OK   ] $m" -ForegroundColor Green }
function Write-Error2($m) { Write-Host "[ERROR] $m" -ForegroundColor Red }

# ============================================================================
# Step 1: Verify Docker is running
# ============================================================================
Write-Info "Checking Docker availability..."
try {
  $dockerVersion = docker --version
  Write-Success "Docker is available: $dockerVersion"
} catch {
  Write-Error2 "Docker is not running. Please start Docker Desktop."
  exit 1
}

# ============================================================================
# Step 2: Ensure modernization-network exists
# ============================================================================
Write-Info "Ensuring modernization-network exists..."
$networkExists = docker network ls --format "{{.Name}}" | Select-String -SimpleMatch "modernization-network"
if (-not $networkExists) {
  Write-Warn "Creating modernization-network..."
  docker network create modernization-network | Out-Null
  Write-Success "Network created: modernization-network"
} else {
  Write-Success "Network already exists: modernization-network"
}

# ============================================================================
# Step 3: Create runner configuration file
# ============================================================================
Write-Info "Creating runner configuration with DinD support..."

$configContent = @"
concurrent = $Concurrent
check_interval = 0
shutdown_timeout = 0

[session_server]
  session_timeout = 1800

[[runners]]
  name = "$RunnerName"
  url = "$GitLabUrl"
  token = "$RunnerToken"
  executor = "docker"
  clone_url = "$GitLabUrl"
  shell = "sh"
  
  [runners.custom_build_dir]
    enabled = false
  
  [runners.cache]
    [runners.cache.s3]
    [runners.cache.gcs]
    [runners.cache.azure]
  
  [runners.docker]
    # Docker-in-Docker settings
    tls_verify = false
    image = "docker:24-cli"
    privileged = true
    disable_entrypoint_overwrite = false
    oom_kill_disable = false
    disable_cache = false
    volumes = ["/cache", "/var/run/docker.sock:/var/run/docker.sock"]
    shm_size = 2147483648  # 2GB shared memory for Docker operations
    network_mode = "modernization-network"
    
    # DinD service for running docker commands
    [[runners.docker.services]]
      name = "docker:24-dind"
      alias = "docker"
      command = ["--tls=false"]
    
    [runners.docker.services.extra_hosts]
      "docker" = "127.0.0.1"
      "nexus-docker" = "127.0.0.1"
"@

# Create .gitlab-runners directory if it doesn't exist
$runnersDir = "$env:USERPROFILE\.gitlab-runner"
if (-not (Test-Path $runnersDir)) {
  New-Item -ItemType Directory -Path $runnersDir | Out-Null
  Write-Info "Created directory: $runnersDir"
}

$configPath = Join-Path $runnersDir "config.toml"
Set-Content -Path $configPath -Value $configContent -Force
Write-Success "Configuration saved: $configPath"

# ============================================================================
# Step 4: Display runner docker command and instructions
# ============================================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "RUNNER SETUP - NEXT STEPS" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

Write-Host "Run the GitLab Runner container with this command:" -ForegroundColor Cyan
Write-Host ""

$dockerCmd = @"
docker run -d `
  --name gitlab-runner `
  --restart unless-stopped `
  --network modernization-network `
  -v "$runnersDir/config.toml:/etc/gitlab-runner/config.toml:ro" `
  -v /var/run/docker.sock:/var/run/docker.sock `
  -e GITLAB_RUNNER_LISTEN_ADDRESS=0.0.0.0:8093 `
  gitlab/gitlab-runner:latest
"@

Write-Host $dockerCmd -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# Step 5: Optional - Run the runner immediately
# ============================================================================
$runNow = Read-Host "Run the runner now? (y/n)"
if ($runNow -eq "y" -or $runNow -eq "Y") {
  Write-Info "Starting GitLab Runner..."
  
  # Stop existing runner if running
  $running = docker ps --format "{{.Names}}" | Select-String -SimpleMatch "gitlab-runner"
  if ($running) {
    Write-Warn "Stopping existing gitlab-runner container..."
    docker stop gitlab-runner | Out-Null
    docker rm gitlab-runner | Out-Null
  }
  
  # Start new runner
  docker run -d `
    --name gitlab-runner `
    --restart unless-stopped `
    --network modernization-network `
    -v "$runnersDir/config.toml:/etc/gitlab-runner/config.toml:ro" `
    -v /var/run/docker.sock:/var/run/docker.sock `
    -e GITLAB_RUNNER_LISTEN_ADDRESS=0.0.0.0:8093 `
    gitlab/gitlab-runner:latest | Out-Null
  
  Write-Success "GitLab Runner started successfully!"
  Write-Info "View logs: docker logs -f gitlab-runner"
} else {
  Write-Info "Runner setup configuration complete. Run the command above when ready."
}

# ============================================================================
# Step 6: Provide additional configuration guidance
# ============================================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "IMPORTANT CONFIGURATION NOTES" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

Write-Host "1. DOCKER-IN-DOCKER (DinD):" -ForegroundColor Cyan
Write-Host "   - Uses docker:24-dind service with --tls=false for reliability"
Write-Host "   - Privileged mode enabled for full Docker access"
Write-Host "   - 2GB shared memory allocated for build operations"
Write-Host ""

Write-Host "2. NETWORK CONFIGURATION:" -ForegroundColor Cyan
Write-Host "   - Runner uses modernization-network bridge"
Write-Host "   - All services on this network can communicate by container name"
Write-Host "   - Nexus accessible as: nexus-docker:5001"
Write-Host ""

Write-Host "3. ENVIRONMENT VARIABLES IN .gitlab-ci.yml:" -ForegroundColor Cyan
Write-Host "   Add these to your CI pipeline for Docker registry access:"
Write-Host ""
Write-Host "   variables:" -ForegroundColor Green
Write-Host "     DOCKER_HOST: tcp://docker:2375" -ForegroundColor Green
Write-Host "     DOCKER_TLS_CERTDIR: ''''" -ForegroundColor Green
Write-Host "     DOCKER_DRIVER: overlay2" -ForegroundColor Green
Write-Host "     DOCKER_REGISTRY: nexus-docker:5001" -ForegroundColor Green
Write-Host "     DOCKER_IMAGE_NAME: java-app" -ForegroundColor Green
Write-Host ""

Write-Host "4. CI/CD SCRIPT EXAMPLE:" -ForegroundColor Cyan
Write-Host "   docker login -u `$DOCKER_REGISTRY_USER -p `$DOCKER_REGISTRY_PASSWORD `$DOCKER_REGISTRY" -ForegroundColor Green
Write-Host "   docker build -t `$DOCKER_REGISTRY/`$DOCKER_IMAGE_NAME:latest ." -ForegroundColor Green
Write-Host "   docker push `$DOCKER_REGISTRY/`$DOCKER_IMAGE_NAME:latest" -ForegroundColor Green
Write-Host ""

Write-Host "5. NEXUS REGISTRY CREDENTIALS:" -ForegroundColor Cyan
Write-Host "   Set these as GitLab CI/CD variables (Settings > CI/CD > Variables):"
Write-Host ""
Write-Host "   - DOCKER_REGISTRY_USER: <nexus-username>" -ForegroundColor Green
Write-Host "   - DOCKER_REGISTRY_PASSWORD: <nexus-password> (masked)" -ForegroundColor Green
Write-Host ""

Write-Host "6. VERIFY RUNNER:" -ForegroundColor Cyan
Write-Host "   docker ps | findstr gitlab-runner" -ForegroundColor Green
Write-Host "   docker logs -f gitlab-runner" -ForegroundColor Green
Write-Host ""

Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""
