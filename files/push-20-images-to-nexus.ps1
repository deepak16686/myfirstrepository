<#
push-20-images-to-nexus.ps1

Pushes 20 images into an existing Nexus Docker hosted repo.
Assumptions:
- Nexus UI is on http://localhost:8081 (optional check)
- Docker registry connector is http://localhost:5001
- Hosted repo is named "apm-repo" (as you stated) and is reachable via localhost:5001
- Insecure registry already configured in Docker Desktop for localhost:5001

Run:
  .\push-20-images-to-nexus.ps1 -NexusUser admin -NexusPassword "YOURPASS"
#>

param(
  [Parameter(Mandatory=$true)]
  [string]$NexusUser,

  [Parameter(Mandatory=$true)]
  [string]$NexusPassword,

  [string]$RegistryHost = "localhost",
  [int]$RegistryPort = 5001,

  # Your docker hosted repo name in Nexus
  [string]$HostedRepoName = "apm-repo",

  # Namespace/prefix inside the repo; keeps things tidy
  [string]$Namespace = "demo"
)

$ErrorActionPreference = "Stop"

function Info($m){ Write-Host "[INFO ] $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "[WARN ] $m" -ForegroundColor Yellow }
function Err ($m){ Write-Host "[ERROR] $m" -ForegroundColor Red }

$Registry = "$RegistryHost`:$RegistryPort"

function Assert-Docker {
  Info "Checking Docker daemon..."
  docker version | Out-Null
}

function Assert-RegistryUp {
  Info "Checking registry endpoint: http://$Registry/v2/"
  try {
    $r = (Invoke-WebRequest -UseBasicParsing -Method Get -Uri "http://$Registry/v2/" -TimeoutSec 10)
    # 200 or 401 are both acceptable for /v2/
    if($r.StatusCode -ne 200 -and $r.StatusCode -ne 401){
      throw "Unexpected status code: $($r.StatusCode)"
    }
    Info "Registry reachable (HTTP $($r.StatusCode))."
  } catch {
    # Some Nexus setups return 401 w/out body; Invoke-WebRequest can throw. We'll tolerate if reachable.
    Warn "Registry check threw: $($_.Exception.Message). Continuing (often harmless if 401)."
  }
}

function Docker-Login {
  Info "Logging into Nexus registry $Registry as $NexusUser ..."
  # Use --password-stdin to avoid leaking in process list
  $NexusPassword | docker login $Registry -u $NexusUser --password-stdin | Out-Null
  Info "docker login succeeded."
}

function Get-RunningImages {
  Info "Collecting images from currently running containers..."
  $imgs = docker ps --format "{{.Image}}" | Sort-Object -Unique
  return @($imgs)
}

function Get-LocalImages {
  # local images (repo:tag), used to prefer ones already present
  return @(docker images --format "{{.Repository}}:{{.Tag}}" | Where-Object { $_ -notmatch "<none>" } | Sort-Object -Unique)
}

function Ensure-Pulled([string]$image){
  $locals = Get-LocalImages
  if($locals -contains $image){
    Info "Already present locally: $image"
    return
  }
  Info "Pulling: $image"
  docker pull $image | Out-Null
}

function Tag-And-Push([string]$src, [string]$dest){
  Info "Tag:  $src  ->  $dest"
  docker tag $src $dest

  Info "Push: $dest"
  docker push $dest | Out-Null
}

# Build a candidate list:
# 1) Prefer images already running
# 2) Add common images until we have enough unique sources
$running = Get-RunningImages

# Add a curated list to reach 20 (small/standard images)
$extras = @(
  "alpine:3.20",
  "busybox:1.36",
  "hello-world:latest",
  "nginx:1.27-alpine",
  "httpd:2.4-alpine",
  "traefik:v3.1",
  "registry:2",
  "rabbitmq:3-alpine",
  "memcached:1.6-alpine",
  "hashicorp/vault:1.17",
  "grafana/grafana:11.1.0",
  "prom/prometheus:v2.55.0",
  "bitnami/kubectl:latest",
  "bitnami/redis:7.2",
  "bitnami/postgresql:15",
  "node:20-alpine",
  "python:3.12-alpine",
  "openjdk:21-jdk-slim",
  "debian:bookworm-slim",
  "ubuntu:24.04",
  "curlimages/curl:8.10.1",
  "mcr.microsoft.com/dotnet/runtime:8.0",
  "mcr.microsoft.com/powershell:7.4-alpine",
  "busybox:stable",
  "alpine:latest"
)


# Merge, preserve order, unique
$candidates = New-Object System.Collections.Generic.List[string]
foreach($i in $running){ if(-not $candidates.Contains($i)){ $candidates.Add($i) } }
foreach($i in $extras){ if(-not $candidates.Contains($i)){ $candidates.Add($i) } }

# We need 20 source images. Trim or pad.
if($candidates.Count -lt 20){
  throw "Not enough candidates to reach 20 (got $($candidates.Count)). Add more extras."
}
$sourceImages = $candidates.GetRange(0,20)

# MAIN
Assert-Docker
Assert-RegistryUp
Docker-Login

Info "Preparing to push exactly 20 images into $Registry/$HostedRepoName ..."
Info "Namespace inside repo: $Namespace"
Write-Host ""

# Push with deterministic naming:
# dest = localhost:5001/apm-repo/demo/<sanitized-name>:demo-XX
# Example: localhost:5001/apm-repo/demo/postgres-15-alpine:demo-01
$index = 1
foreach($src in $sourceImages){

  # Ensure local pull to avoid push failures
  Ensure-Pulled $src

  # sanitize repo name for destination path
  $safe = $src.ToLower()
  $safe = $safe -replace "[^a-z0-9\/\.\-\:]", "-"   # conservative
  $safe = $safe -replace "[:]", "-"                 # remove tag separator from path component
  $safe = $safe -replace "[\/\.]", "-"              # simplify to single segment
  $safe = $safe.Trim("-")

  $tag = ("demo-{0:d2}" -f $index)

  # Destination path: <registry>/<repo>/<namespace>/<image-name>:<tag>
  $dest = "$Registry/$HostedRepoName/$Namespace/$safe`:$tag"

  Tag-And-Push -src $src -dest $dest
  $index++
}

Write-Host ""
Info "Done. 20 images pushed."
Info "You can validate in Nexus UI under: Browse -> $HostedRepoName"
Info "Example pull:"
Write-Host "  docker pull $Registry/$HostedRepoName/$Namespace/postgres-15-alpine:demo-01"
