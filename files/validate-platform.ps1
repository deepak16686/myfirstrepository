# ============================================================================
# Platform Health Check & Validation Script
# ============================================================================
# Quick validation of all platform services
# ============================================================================

param(
    [switch]$Detailed,
    [switch]$Continuous,
    [int]$Interval = 30
)

$ErrorActionPreference = "SilentlyContinue"

function Test-Port {
    param([int]$Port)
    $connection = Test-NetConnection -ComputerName localhost -Port $Port -WarningAction SilentlyContinue
    return $connection.TcpTestSucceeded
}

function Get-ServiceStatus {
    param(
        [string]$Name,
        [int]$Port,
        [string]$ContainerName
    )
    
    $status = @{
        Name = $Name
        Port = $Port
        Container = $ContainerName
        PortOpen = Test-Port -Port $Port
        ContainerRunning = $false
        ContainerHealth = "N/A"
    }
    
    # Check container status
    $container = docker ps --filter "name=$ContainerName" --format "{{.Status}}" 2>&1
    if ($container -and $container -notlike "*error*") {
        $status.ContainerRunning = $true
        
        # Check health if available
        $health = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>&1
        if ($health -and $health -ne "<no value>") {
            $status.ContainerHealth = $health
        }
    }
    
    return $status
}

function Show-ServiceStatus {
    param($Status)
    
    $symbol = if ($Status.PortOpen -and $Status.ContainerRunning) { "✓" } else { "✗" }
    $color = if ($Status.PortOpen -and $Status.ContainerRunning) { "Green" } else { "Red" }
    
    Write-Host "$symbol " -ForegroundColor $color -NoNewline
    Write-Host "$($Status.Name.PadRight(20))" -NoNewline
    Write-Host "Port: $($Status.Port.ToString().PadLeft(5)) " -NoNewline
    
    if ($Status.PortOpen) {
        Write-Host "OPEN " -ForegroundColor Green -NoNewline
    } else {
        Write-Host "CLOSED " -ForegroundColor Red -NoNewline
    }
    
    Write-Host "| Container: " -NoNewline
    if ($Status.ContainerRunning) {
        Write-Host "RUNNING " -ForegroundColor Green -NoNewline
    } else {
        Write-Host "STOPPED " -ForegroundColor Red -NoNewline
    }
    
    if ($Status.ContainerHealth -ne "N/A") {
        Write-Host "| Health: $($Status.ContainerHealth)" -ForegroundColor Yellow
    } else {
        Write-Host ""
    }
}

function Test-AllServices {
    Write-Host "`n$('=' * 80)" -ForegroundColor Cyan
    Write-Host "  Platform Health Check - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
    Write-Host "$('=' * 80)`n" -ForegroundColor Cyan
    
    $services = @(
        @{Name="PostgreSQL"; Port=5432; Container="postgres"}
        @{Name="Redis"; Port=6379; Container="redis"}
        @{Name="MinIO"; Port=9000; Container="minio"}
        @{Name="MinIO Console"; Port=9001; Container="minio"}
        @{Name="ChromaDB"; Port=8000; Container="chromadb"}
        @{Name="Ollama"; Port=11434; Container="ollama"}
        @{Name="Prometheus"; Port=9090; Container="prometheus"}
        @{Name="Grafana"; Port=3000; Container="grafana"}
        @{Name="Loki"; Port=3100; Container="loki"}
        @{Name="Jaeger"; Port=16686; Container="jaeger"}
    )
    
    $allHealthy = $true
    $results = @()
    
    foreach ($service in $services) {
        $status = Get-ServiceStatus -Name $service.Name -Port $service.Port -ContainerName $service.Container
        $results += $status
        Show-ServiceStatus -Status $status
        
        if (-not ($status.PortOpen -and $status.ContainerRunning)) {
            $allHealthy = $false
        }
    }
    
    Write-Host "`n$('-' * 80)" -ForegroundColor Gray
    
    if ($allHealthy) {
        Write-Host "Overall Status: " -NoNewline
        Write-Host "ALL SERVICES HEALTHY ✓" -ForegroundColor Green
    } else {
        Write-Host "Overall Status: " -NoNewline
        Write-Host "SOME SERVICES DOWN ✗" -ForegroundColor Red
    }
    
    Write-Host "$('-' * 80)`n" -ForegroundColor Gray
    
    return $allHealthy
}

function Show-DetailedInfo {
    Write-Host "`n$('=' * 80)" -ForegroundColor Cyan
    Write-Host "  Detailed Platform Information" -ForegroundColor Cyan
    Write-Host "$('=' * 80)`n" -ForegroundColor Cyan
    
    # Docker info
    Write-Host "Docker Information:" -ForegroundColor Yellow
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>&1
    Write-Host "  Version: $dockerVersion"
    
    # Container stats
    Write-Host "`nRunning Containers:" -ForegroundColor Yellow
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Out-String | Write-Host
    
    # Ollama models
    Write-Host "`nInstalled AI Models:" -ForegroundColor Yellow
    docker exec ollama ollama list 2>&1 | Write-Host
    
    # Network info
    Write-Host "`nDocker Networks:" -ForegroundColor Yellow
    docker network ls --filter name=modernization --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}" | Out-String | Write-Host
    
    # Volume info
    Write-Host "`nDocker Volumes:" -ForegroundColor Yellow
    docker volume ls --filter name=data --format "table {{.Name}}\t{{.Driver}}" | Out-String | Write-Host
    
    # Resource usage
    Write-Host "`nResource Usage (Top 5 by CPU):" -ForegroundColor Yellow
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" | Select-Object -First 6 | Write-Host
}

function Test-Connectivity {
    Write-Host "`n$('=' * 80)" -ForegroundColor Cyan
    Write-Host "  Testing Service Connectivity" -ForegroundColor Cyan
    Write-Host "$('=' * 80)`n" -ForegroundColor Cyan
    
    # Test Ollama
    Write-Host "Testing Ollama API... " -NoNewline
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 5
        Write-Host "✓ SUCCESS" -ForegroundColor Green
        Write-Host "  Models available: $($response.models.Count)"
    } catch {
        Write-Host "✗ FAILED" -ForegroundColor Red
    }
    
    # Test ChromaDB
    Write-Host "Testing ChromaDB API... " -NoNewline
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/heartbeat" -Method Get -TimeoutSec 5
        Write-Host "✓ SUCCESS" -ForegroundColor Green
    } catch {
        Write-Host "✗ FAILED" -ForegroundColor Red
    }
    
    # Test Prometheus
    Write-Host "Testing Prometheus API... " -NoNewline
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:9090/-/healthy" -Method Get -TimeoutSec 5
        Write-Host "✓ SUCCESS" -ForegroundColor Green
    } catch {
        Write-Host "✗ FAILED" -ForegroundColor Red
    }
    
    # Test MinIO
    Write-Host "Testing MinIO API... " -NoNewline
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:9000/minio/health/live" -Method Get -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Host "✓ SUCCESS" -ForegroundColor Green
        }
    } catch {
        Write-Host "✗ FAILED" -ForegroundColor Red
    }
    
    Write-Host ""
}

# Main execution
do {
    Clear-Host
    $healthy = Test-AllServices
    
    if ($Detailed) {
        Show-DetailedInfo
        Test-Connectivity
    }
    
    if ($Continuous) {
        Write-Host "`nNext check in $Interval seconds... (Press Ctrl+C to stop)" -ForegroundColor Yellow
        Start-Sleep -Seconds $Interval
    }
} while ($Continuous)

Write-Host "`nValidation complete!`n" -ForegroundColor Green
