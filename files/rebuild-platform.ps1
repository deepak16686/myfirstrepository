#Requires -Version 5.1

<#
.SYNOPSIS
    Legacy Application Modernization Platform - Complete Infrastructure Rebuild
.DESCRIPTION
    Rebuilds entire Docker infrastructure including PostgreSQL, Redis, MinIO, ChromaDB, Ollama, and Open WebUI
.PARAMETER SkipModels
    Skip downloading AI models (DeepSeek Coder, CodeLlama, Qwen2.5-Coder)
.PARAMETER SkipMonitoring
    Skip deploying monitoring stack (Prometheus, Grafana, Loki, Jaeger)
.PARAMETER Validate
    Only validate the deployment without making changes
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [switch]$SkipModels,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipMonitoring,
    
    [Parameter(Mandatory=$false)]
    [switch]$Validate
)

$ErrorActionPreference = "Stop"

Write-Host "=============================================================================" -ForegroundColor Cyan
Write-Host "   Legacy Application Modernization Platform - Rebuild Script" -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan

# Configuration
$NETWORKS = @{
    Modernization = "modernization-network"
    Monitoring = "monitoring-network"
}

$CONTAINERS = @{
    PostgreSQL = "postgres"
    Redis = "redis"
    MinIO = "minio"
    ChromaDB = "chromadb"
    Ollama = "ollama"
    OpenWebUI = "open-webui"
    Prometheus = "prometheus"
    Grafana = "grafana"
    Loki = "loki"
    Jaeger = "jaeger"
}

$PORTS = @{
    PostgreSQL = 5432
    Redis = 6379
    MinIO = 9000
    MinIOConsole = 9001
    ChromaDB = 8000
    Ollama = 11434
    OpenWebUI = 3001
    Prometheus = 9090
    Grafana = 3000
    Loki = 3100
    JaegerUI = 16686
}

$VOLUMES = @{
    PostgreSQL = "postgres-data"
    Redis = "redis-data"
    MinIO = "minio-data"
    ChromaDB = "chromadb-data"
    Ollama = "ollama-models"
    OpenWebUI = "open-webui-data"
    Prometheus = "prometheus-data"
    Grafana = "grafana-data"
    Loki = "loki-data"
}

$AI_MODELS = @(
    "deepseek-coder:33b"
    "codellama:7b"
    "qwen2.5-coder:32b"
)

function Write-Step {
    param([string]$Message)
    Write-Host "`n>>> $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "    [OK] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "    [ERROR] $Message" -ForegroundColor Red
}

# Step 1: Validate Docker
Write-Step "Validating Docker installation..."
try {
    $dockerVersion = docker --version
    Write-Success "Docker is installed: $dockerVersion"
} catch {
    Write-Error "Docker is not installed or not running"
    exit 1
}

if ($Validate) {
    Write-Host "`nValidation complete. Use without -Validate to deploy." -ForegroundColor Green
    exit 0
}

# Step 2: Cleanup existing containers
Write-Step "Cleaning up existing containers..."
$allContainers = $CONTAINERS.Values
foreach ($container in $allContainers) {
    $exists = docker ps -a --format "{{.Names}}" | Select-String -Pattern "^$container$"
    if ($exists) {
        Write-Host "    Removing container: $container" -ForegroundColor Gray
        docker rm -f $container 2>$null | Out-Null
    }
}
Write-Success "Cleanup complete"

# Step 3: Create networks
Write-Step "Creating Docker networks..."
foreach ($network in $NETWORKS.Values) {
    $exists = docker network ls --format "{{.Name}}" | Select-String -Pattern "^$network$"
    if (-not $exists) {
        docker network create $network | Out-Null
        Write-Success "Created network: $network"
    } else {
        Write-Host "    Network already exists: $network" -ForegroundColor Gray
    }
}

# Step 4: Deploy PostgreSQL
Write-Step "Deploying PostgreSQL..."
docker run -d `
    --name $CONTAINERS.PostgreSQL `
    --network $NETWORKS.Modernization `
    -p "$($PORTS.PostgreSQL):5432" `
    -e POSTGRES_USER=admin `
    -e POSTGRES_PASSWORD=admin123 `
    -e POSTGRES_DB=modernization `
    -v "$($VOLUMES.PostgreSQL):/var/lib/postgresql/data" `
    --restart unless-stopped `
    postgres:16-alpine | Out-Null
Write-Success "PostgreSQL deployed on port $($PORTS.PostgreSQL)"

# Step 5: Deploy Redis
Write-Step "Deploying Redis..."
docker run -d `
    --name $CONTAINERS.Redis `
    --network $NETWORKS.Modernization `
    -p "$($PORTS.Redis):6379" `
    -v "$($VOLUMES.Redis):/data" `
    --restart unless-stopped `
    redis:7-alpine | Out-Null
Write-Success "Redis deployed on port $($PORTS.Redis)"

# Step 6: Deploy MinIO
Write-Step "Deploying MinIO..."
docker run -d `
    --name $CONTAINERS.MinIO `
    --network $NETWORKS.Modernization `
    -p "$($PORTS.MinIO):9000" `
    -p "$($PORTS.MinIOConsole):9001" `
    -e MINIO_ROOT_USER=admin `
    -e MINIO_ROOT_PASSWORD=admin123 `
    -v "$($VOLUMES.MinIO):/data" `
    --restart unless-stopped `
    minio/minio server /data --console-address ":9001" | Out-Null
Write-Success "MinIO deployed on ports $($PORTS.MinIO) and $($PORTS.MinIOConsole)"

# Step 7: Deploy ChromaDB
Write-Step "Deploying ChromaDB..."
docker run -d `
    --name $CONTAINERS.ChromaDB `
    --network $NETWORKS.Modernization `
    -p "$($PORTS.ChromaDB):8000" `
    -v "$($VOLUMES.ChromaDB):/chroma/chroma" `
    --restart unless-stopped `
    chromadb/chroma:latest | Out-Null
Write-Success "ChromaDB deployed on port $($PORTS.ChromaDB)"

# Step 8: Deploy Ollama
Write-Step "Deploying Ollama with GPU support..."
docker run -d `
    --name $CONTAINERS.Ollama `
    --network $NETWORKS.Modernization `
    -p "$($PORTS.Ollama):11434" `
    -v "$($VOLUMES.Ollama):/root/.ollama" `
    --gpus all `
    --restart unless-stopped `
    ollama/ollama:latest | Out-Null
Write-Success "Ollama deployed on port $($PORTS.Ollama)"

Start-Sleep -Seconds 5

# Step 9: Deploy Open WebUI
Write-Step "Deploying Open WebUI..."
docker run -d `
    --name $CONTAINERS.OpenWebUI `
    --network $NETWORKS.Modernization `
    -p "$($PORTS.OpenWebUI):8080" `
    -e OLLAMA_BASE_URL=http://ollama:11434 `
    -e WEBUI_SECRET_KEY=modernization-secret-key-2024 `
    -v "$($VOLUMES.OpenWebUI):/app/backend/data" `
    --restart unless-stopped `
    ghcr.io/open-webui/open-webui:main | Out-Null
Write-Success "Open WebUI deployed on port $($PORTS.OpenWebUI)"

# Step 10: Download AI Models
if (-not $SkipModels) {
    Write-Step "Downloading AI models (this may take a while)..."
    foreach ($model in $AI_MODELS) {
        Write-Host "    Pulling model: $model" -ForegroundColor Cyan
        docker exec $CONTAINERS.Ollama ollama pull $model
    }
    Write-Success "All AI models downloaded"
} else {
    Write-Host "`n>>> Skipping AI model downloads (use without -SkipModels to download)" -ForegroundColor Yellow
}

# Step 11: Deploy Monitoring Stack
if (-not $SkipMonitoring) {
    Write-Step "Deploying monitoring stack..."
    
    # Prometheus
    docker run -d `
        --name $CONTAINERS.Prometheus `
        --network $NETWORKS.Monitoring `
        -p "$($PORTS.Prometheus):9090" `
        -v "$($VOLUMES.Prometheus):/prometheus" `
        --restart unless-stopped `
        prom/prometheus:latest | Out-Null
    
    # Grafana
    docker run -d `
        --name $CONTAINERS.Grafana `
        --network $NETWORKS.Monitoring `
        -p "$($PORTS.Grafana):3000" `
        -e GF_SECURITY_ADMIN_PASSWORD=admin123 `
        -v "$($VOLUMES.Grafana):/var/lib/grafana" `
        --restart unless-stopped `
        grafana/grafana:latest | Out-Null
    
    # Loki
    docker run -d `
        --name $CONTAINERS.Loki `
        --network $NETWORKS.Monitoring `
        -p "$($PORTS.Loki):3100" `
        -v "$($VOLUMES.Loki):/loki" `
        --restart unless-stopped `
        grafana/loki:latest | Out-Null
    
    # Jaeger
    docker run -d `
        --name $CONTAINERS.Jaeger `
        --network $NETWORKS.Monitoring `
        -p "$($PORTS.JaegerUI):16686" `
        --restart unless-stopped `
        jaegertracing/all-in-one:latest | Out-Null
    
    Write-Success "Monitoring stack deployed"
} else {
    Write-Host "`n>>> Skipping monitoring stack (use without -SkipMonitoring to deploy)" -ForegroundColor Yellow
}

# Step 12: Final Validation
Write-Step "Running final validation..."

Write-Host "`n=============================================================================" -ForegroundColor Cyan
Write-Host "                    DEPLOYMENT STATUS REPORT                              " -ForegroundColor Cyan
Write-Host "=============================================================================" -ForegroundColor Cyan

$runningContainers = docker ps --format "{{.Names}}" | ForEach-Object { $_.Trim() }

Write-Host "`n[Infrastructure Services]" -ForegroundColor Yellow
@(
    @{Name="PostgreSQL"; Container=$CONTAINERS.PostgreSQL; Port=$PORTS.PostgreSQL}
    @{Name="Redis"; Container=$CONTAINERS.Redis; Port=$PORTS.Redis}
    @{Name="MinIO"; Container=$CONTAINERS.MinIO; Port=$PORTS.MinIO}
    @{Name="ChromaDB"; Container=$CONTAINERS.ChromaDB; Port=$PORTS.ChromaDB}
    @{Name="Ollama"; Container=$CONTAINERS.Ollama; Port=$PORTS.Ollama}
    @{Name="Open WebUI"; Container=$CONTAINERS.OpenWebUI; Port=$PORTS.OpenWebUI}
) | ForEach-Object {
    $status = if ($runningContainers -contains $_.Container) { "[RUNNING]" } else { "[STOPPED]" }
    $color = if ($runningContainers -contains $_.Container) { "Green" } else { "Red" }
    Write-Host ("  {0,-20} : localhost:{1,-5} - {2}" -f $_.Name, $_.Port, $status) -ForegroundColor $color
}

if (-not $SkipMonitoring) {
    Write-Host "`n[Monitoring Services]" -ForegroundColor Yellow
    @(
        @{Name="Prometheus"; Container=$CONTAINERS.Prometheus; Port=$PORTS.Prometheus}
        @{Name="Grafana"; Container=$CONTAINERS.Grafana; Port=$PORTS.Grafana}
        @{Name="Loki"; Container=$CONTAINERS.Loki; Port=$PORTS.Loki}
        @{Name="Jaeger"; Container=$CONTAINERS.Jaeger; Port=$PORTS.JaegerUI}
    ) | ForEach-Object {
        $status = if ($runningContainers -contains $_.Container) { "[RUNNING]" } else { "[STOPPED]" }
        $color = if ($runningContainers -contains $_.Container) { "Green" } else { "Red" }
        Write-Host ("  {0,-20} : localhost:{1,-5} - {2}" -f $_.Name, $_.Port, $status) -ForegroundColor $color
    }
}

# Network Status
Write-Host "`n[Docker Networks]" -ForegroundColor Yellow
$networks = docker network ls --format "{{.Name}}" | Where-Object { $_ -match "modernization|monitoring" }
foreach ($network in $networks) {
    Write-Host "  - $network" -ForegroundColor Cyan
}

# Volume Status
Write-Host "`n[Docker Volumes]" -ForegroundColor Yellow
$volumes = docker volume ls --format "{{.Name}}" | Where-Object { $_ -match "postgres|redis|minio|chromadb|ollama|open-webui|prometheus|grafana|loki" }
foreach ($volume in $volumes) {
    Write-Host "  - $volume" -ForegroundColor Cyan
}

# AI Models Status
if (-not $SkipModels) {
    Write-Host "`n[AI Models Installed]" -ForegroundColor Yellow
    try {
        $modelsList = docker exec $CONTAINERS.Ollama ollama list 2>&1
        Write-Host $modelsList -ForegroundColor Gray
    } catch {
        Write-Host "  [WARNING] Unable to retrieve model list" -ForegroundColor Yellow
    }
}

Write-Host "`n=============================================================================" -ForegroundColor Cyan
Write-Host "   DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "=============================================================================" -ForegroundColor Cyan

Write-Host "`n[Quick Access URLs]" -ForegroundColor Yellow
Write-Host "  - PostgreSQL        : localhost:$($PORTS.PostgreSQL)" -ForegroundColor White
Write-Host "  - Redis             : localhost:$($PORTS.Redis)" -ForegroundColor White
Write-Host "  - MinIO Console     : http://localhost:$($PORTS.MinIOConsole)" -ForegroundColor White
Write-Host "  - ChromaDB          : http://localhost:$($PORTS.ChromaDB)" -ForegroundColor White
Write-Host "  - Ollama API        : http://localhost:$($PORTS.Ollama)" -ForegroundColor White
Write-Host "  - Open WebUI        : http://localhost:$($PORTS.OpenWebUI)" -ForegroundColor Cyan -BackgroundColor DarkBlue

if (-not $SkipMonitoring) {
    Write-Host "`n  - Prometheus        : http://localhost:$($PORTS.Prometheus)" -ForegroundColor White
    Write-Host "  - Grafana           : http://localhost:$($PORTS.Grafana) (admin/admin123)" -ForegroundColor White
    Write-Host "  - Loki              : http://localhost:$($PORTS.Loki)" -ForegroundColor White
    Write-Host "  - Jaeger            : http://localhost:$($PORTS.JaegerUI)" -ForegroundColor White
}

Write-Host "`n[Next Steps]" -ForegroundColor Yellow
Write-Host "  1. Access Open WebUI at http://localhost:$($PORTS.OpenWebUI)" -ForegroundColor Gray
Write-Host "  2. Create your admin account" -ForegroundColor Gray
Write-Host "  3. Start chatting with the AI models!" -ForegroundColor Gray

Write-Host "`n[Useful Commands]" -ForegroundColor Yellow
Write-Host "  - View logs         : docker logs -f <container-name>" -ForegroundColor Gray
Write-Host "  - Resource usage    : docker stats" -ForegroundColor Gray
Write-Host "  - List models       : docker exec ollama ollama list" -ForegroundColor Gray
Write-Host "  - Stop all          : docker stop " -NoNewline -ForegroundColor Gray
Write-Host ($CONTAINERS.Values -join " ") -ForegroundColor Cyan

Write-Host "`n"
