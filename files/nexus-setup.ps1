<# 
nexus-setup.ps1
- Idempotent Nexus bring-up for Docker Desktop demo environment
- Network: ai-platform-net
- Container: ai-nexus
- Volume: nexus-data
- Ports: 8081 (UI), 5001 (Docker registry connector)

Usage:
  .\nexus-setup.ps1
#>

$ErrorActionPreference = "Stop"

# -----------------------------
# Config
# -----------------------------
$NetworkName   = "ai-platform-net"
$ContainerName = "ai-nexus"
$Image         = "sonatype/nexus3:latest"
$DataVolume    = "nexus-data"
$UiPort        = 8081
$DockerPort    = 5001

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir    = Join-Path $ScriptDir "logs"
$NexusLog  = Join-Path $LogDir "nexus.log"

# -----------------------------
# Helpers
# -----------------------------
function Write-Info($msg)  { Write-Host "[INFO ] $msg" -ForegroundColor Cyan }
function Write-Warn($msg)  { Write-Host "[WARN ] $msg" -ForegroundColor Yellow }
function Write-Err ($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Ensure-Dir($path) {
  if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
}

function Ensure-DockerRunning {
  docker version *> $null
  Write-Info "Docker engine reachable."
}

function Ensure-Network($name) {
  $exists = docker network ls --format "{{.Name}}" | Where-Object { $_ -eq $name }
  if (-not $exists) {
    Write-Info "Creating network: $name"
    docker network create $name | Out-Null
  } else {
    Write-Info "Network exists: $name"
  }
}

function Ensure-Volume($name) {
  $exists = docker volume ls --format "{{.Name}}" | Where-Object { $_ -eq $name }
  if (-not $exists) {
    Write-Info "Creating volume: $name"
    docker volume create $name | Out-Null
  } else {
    Write-Info "Volume exists: $name"
  }
}

function Stop-Remove-Container($name) {
  $id = docker ps -a --format "{{.ID}} {{.Names}}" | ForEach-Object {
    $parts = $_.Split(" ",2)
    if ($parts.Count -eq 2 -and $parts[1] -eq $name) { $parts[0] }
  }

  if ($id) {
    Write-Info "Removing container: $name"
    try { docker rm -f $name | Out-Null } catch { }
  }
}

function Start-Nexus {
  Write-Info "Starting Nexus container: $ContainerName"
  docker run -d --name $ContainerName --restart unless-stopped `
    --network $NetworkName `
    -p "$UiPort`:8081" -p "$DockerPort`:5001" `
    -v "$DataVolume`:/nexus-data" `
    $Image | Out-Null

  Write-Info "Container started."
}

function Wait-For-Http200($url, [int]$timeoutSec = 240) {
  Write-Info "Waiting for Nexus HTTP 200 at $url (timeout ${timeoutSec}s)..."
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
    try {
      $resp = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 5
      if ($resp.StatusCode -eq 200) {
        Write-Info "Nexus is responding: HTTP 200"
        return
      }
    } catch {
      Start-Sleep -Seconds 3
    }
  }
  throw "Timeout waiting for Nexus to become ready at $url"
}

function Tail-LogsToFile {
  Ensure-Dir $LogDir
  Write-Info "Writing recent Nexus logs to: $NexusLog"
  try {
    docker logs $ContainerName --tail 200 | Out-File -FilePath $NexusLog -Encoding utf8
  } catch {
    Write-Warn "Could not fetch logs (container may not be running yet)."
  }
}

function Show-AdminPasswordIfPresent {
  Write-Info "Checking for /nexus-data/admin.password ..."
  try {
    $out = docker exec $ContainerName sh -lc 'test -f /nexus-data/admin.password && cat /nexus-data/admin.password || true'
    if ([string]::IsNullOrWhiteSpace($out)) {
      Write-Warn "admin.password not found. This usually means the data volume was already initialized and the file was removed after first-run."
      Write-Warn "If you forgot the admin password, use the H2 reset flow (see Enable-H2Console / Disable-H2Console functions)."
    } else {
      Write-Host ""
      Write-Host "Initial admin password (first-run only): $out" -ForegroundColor Green
      Write-Host ""
    }
  } catch {
    Write-Warn "Unable to read admin.password from container."
  }
}

# ---- Optional: H2 console toggles (for password recovery in demo) ----
function Enable-H2Console {
  <#
    Enables the H2 console for password reset workflows.
    After enabling: restart Nexus, then browse http://localhost:1234
    IMPORTANT: Demo only; disable immediately after reset.
  #>
  Write-Warn "Enabling H2 console (demo-only)."
  docker exec $ContainerName sh -lc @'
set -e
PROPS="/nexus-data/etc/nexus.properties"
touch "$PROPS"
grep -q "nexus.h2.httpListenerEnabled" "$PROPS" || echo "nexus.h2.httpListenerEnabled=true" >> "$PROPS"
grep -q "nexus.h2.httpListenerPort" "$PROPS"    || echo "nexus.h2.httpListenerPort=1234" >> "$PROPS"
tail -n 20 "$PROPS"
'@
  Write-Info "Restarting Nexus..."
  docker restart $ContainerName | Out-Null
  Write-Info "H2 console should be reachable at: http://localhost:1234 (once Nexus is up)."
}

function Disable-H2Console {
  Write-Warn "Disabling H2 console."
  docker exec $ContainerName sh -lc @'
set -e
PROPS="/nexus-data/etc/nexus.properties"
[ -f "$PROPS" ] || exit 0
grep -v "nexus.h2.httpListenerEnabled" "$PROPS" | grep -v "nexus.h2.httpListenerPort" > "${PROPS}.tmp"
mv "${PROPS}.tmp" "$PROPS"
tail -n 20 "$PROPS"
'@
  Write-Info "Restarting Nexus..."
  docker restart $ContainerName | Out-Null
}

function Show-Status {
  Write-Info "Container status:"
  docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" | Select-String -Pattern $ContainerName | ForEach-Object { $_.Line }
}

# -----------------------------
# Main
# -----------------------------
try {
  Ensure-DockerRunning
  Ensure-Network $NetworkName
  Ensure-Volume  $DataVolume

  # If container exists but is not running, keep it; otherwise create fresh.
  $existing = docker ps -a --format "{{.Names}} {{.Status}}" | Where-Object { $_ -match "^$ContainerName\s" }
  if (-not $existing) {
    Start-Nexus
  } else {
    $running = docker ps --format "{{.Names}}" | Where-Object { $_ -eq $ContainerName }
    if ($running) {
      Write-Info "Container already running: $ContainerName"
    } else {
      Write-Warn "Container exists but not running. Starting it..."
      docker start $ContainerName | Out-Null
    }
  }

  Wait-For-Http200 "http://localhost:$UiPort/"
  Show-Status
  Tail-LogsToFile
  Show-AdminPasswordIfPresent

  Write-Host ""
  Write-Info "Nexus UI:        http://localhost:$UiPort/"
  Write-Info "Docker registry: http://localhost:$DockerPort/  (configure repo connector in Nexus)"
  Write-Host ""
  Write-Info "Next common tasks:"
  Write-Host "  - Create Docker (hosted) repo in Nexus and bind it to port $DockerPort"
  Write-Host "  - Then test: docker login localhost:$DockerPort"
  Write-Host ""
  Write-Info "If you need password recovery (demo):"
  Write-Host "  - Run: Enable-H2Console   (then reset admin in H2 UI)"
  Write-Host "  - Run: Disable-H2Console  (immediately after reset)"
}
catch {
  Write-Err $_.Exception.Message
  Tail-LogsToFile
  Write-Warn "Recent logs saved at: $NexusLog"
  exit 1
}
