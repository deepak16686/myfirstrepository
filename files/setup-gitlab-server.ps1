<#
GitLab Server only (Docker Desktop)
- Creates/uses: ai-platform-net network
- Creates/uses: ai-gitlab-config, ai-gitlab-data, ai-gitlab-logs volumes
- Starts: ai-gitlab container
- Waits until HTTP is reachable

No runners. No tokens. No API calls.
#>

[CmdletBinding()]
param(
  [int]$GitLabHttpPort = 8082,
  [int]$GitLabSshPort  = 2222,
  [string]$ProjectName = "ai",
  [int]$ReadyTimeoutSec = 1200,
  [string]$RootPassword = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info($m) { Write-Host "[INFO ] $m" -ForegroundColor Cyan }
function Write-Warn($m) { Write-Host "[WARN ] $m" -ForegroundColor Yellow }

function Ensure-Dir($path) {
  if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
}

function Ensure-Network($name) {
  $exists = docker network ls --format "{{.Name}}" | Select-String -SimpleMatch $name
  if (-not $exists) { Write-Info "Creating docker network: $name"; docker network create $name | Out-Null }
  else { Write-Info "Docker network exists: $name" }
}

function Ensure-Volume($name) {
  $exists = docker volume ls --format "{{.Name}}" | Select-String -SimpleMatch $name
  if (-not $exists) { Write-Info "Creating docker volume: $name"; docker volume create $name | Out-Null }
  else { Write-Info "Docker volume exists: $name" }
}

function New-RandomPassword([int]$len = 20) {
  $chars = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  -join (1..$len | ForEach-Object { $chars[(Get-Random -Minimum 0 -Maximum $chars.Length)] })
}

function Wait-HttpReady($url, [int]$timeoutSec) {
  Write-Info "Waiting for GitLab readiness: $url (timeout ${timeoutSec}s)"
  $start = Get-Date
  while ($true) {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -Method Head -TimeoutSec 15
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
        Write-Info "GitLab HTTP endpoint responding (StatusCode=$($resp.StatusCode))."
        break
      }
    } catch { }
    if (((Get-Date) - $start).TotalSeconds -gt $timeoutSec) {
      throw "GitLab did not become ready within ${timeoutSec}s. Check: docker logs $ProjectName-gitlab"
    }
    Start-Sleep -Seconds 10
  }
  Write-Info "Stabilization wait..."
  Start-Sleep -Seconds 20
}

# ---------------- Main ----------------
$netName = "ai-platform-net"
Ensure-Network $netName

# secrets (demo)
$secretsDir = Join-Path (Get-Location) ".secrets"
Ensure-Dir $secretsDir
$rootPassFile = Join-Path $secretsDir "gitlab-root-password.txt"

# Root password handling
if (-not $RootPassword -or $RootPassword.Trim().Length -lt 8) {
  if (Test-Path $rootPassFile) {
    $RootPassword = (Get-Content $rootPassFile -Raw).Trim()
    if ($RootPassword.Length -lt 8) { $RootPassword = New-RandomPassword 20 }
    Write-Info "Using existing root password file: $rootPassFile"
  } else {
    $RootPassword = New-RandomPassword 20
    Set-Content -Path $rootPassFile -Value $RootPassword -NoNewline
    Write-Info "Generated root password saved (demo): $rootPassFile"
  }
} else {
  Set-Content -Path $rootPassFile -Value $RootPassword -NoNewline
  Write-Info "Root password stored (demo): $rootPassFile"
}

# GitLab volumes
Ensure-Volume "$ProjectName-gitlab-config"
Ensure-Volume "$ProjectName-gitlab-data"
Ensure-Volume "$ProjectName-gitlab-logs"

$gitlabName = "$ProjectName-gitlab"
$exists = docker ps -a --format "{{.Names}}" | Select-String -SimpleMatch $gitlabName

if (-not $exists) {
  Write-Info "Starting GitLab container: $gitlabName"
  $externalUrl = "http://localhost:$GitLabHttpPort"

  docker run -d --name $gitlabName --restart unless-stopped `
    --network $netName `
    -p "${GitLabHttpPort}:80" `
    -p "${GitLabSshPort}:22" `
    -v "$ProjectName-gitlab-config:/etc/gitlab" `
    -v "$ProjectName-gitlab-logs:/var/log/gitlab" `
    -v "$ProjectName-gitlab-data:/var/opt/gitlab" `
    -e "EXTERNAL_URL=$externalUrl" `
    -e "GITLAB_ROOT_PASSWORD=$RootPassword" `
    -e "GITLAB_ROOT_EMAIL=admin@example.local" `
    gitlab/gitlab-ee:latest | Out-Null
} else {
  $running = docker ps --format "{{.Names}}" | Select-String -SimpleMatch $gitlabName
  if ($running) {
    Write-Info "GitLab already running: $gitlabName"
  } else {
    Write-Info "Starting existing GitLab container..."
    docker start $gitlabName | Out-Null
  }
}

$gitlabBaseUrl = "http://localhost:$GitLabHttpPort"
Wait-HttpReady -url $gitlabBaseUrl -timeoutSec $ReadyTimeoutSec

Write-Info "Done."
Write-Info "GitLab UI:  $gitlabBaseUrl"
Write-Info "Root user:  root"
Write-Info "Root pass:  (stored in) $rootPassFile"
Write-Info "Logs:       docker logs $gitlabName --tail 100"
