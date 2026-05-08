# =============================================================================
# AI Generator Test Runner
# Orchestrates: Ingest templates -> Start API -> Run tests
# Prerequisites: Docker Desktop running with ChromaDB on port 8000
# =============================================================================

param(
    [switch]$SkipIngest,
    [switch]$SkipAPI,
    [switch]$RetrievalOnly
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  AI Dockerfile & GitLab CI Generator - Test Runner" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan

# Step 0: Check Python and dependencies
Write-Host "`n[STEP 0] Checking Python dependencies..." -ForegroundColor Yellow
python --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python not found. Install Python 3.10+" -ForegroundColor Red
    exit 1
}

# Check required packages
$packages = @("chromadb", "fastapi", "uvicorn", "requests", "pyyaml")
foreach ($pkg in $packages) {
    $installed = python -c "import $pkg" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Installing $pkg..." -ForegroundColor Gray
        pip install $pkg --quiet
    }
}

# Step 1: Verify ChromaDB connectivity
Write-Host "`n[STEP 1] Checking ChromaDB connectivity..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/heartbeat" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "  [OK] ChromaDB is running" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] ChromaDB not reachable on port 8000" -ForegroundColor Red
    Write-Host "  Ensure ChromaDB container is running: docker ps | findstr chroma" -ForegroundColor Gray
    exit 1
}

# Step 2: Ingest templates
if (-not $SkipIngest) {
    Write-Host "`n[STEP 2] Ingesting templates into ChromaDB..." -ForegroundColor Yellow
    python create_collections.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to create collections" -ForegroundColor Red
        exit 1
    }
    python ingest_templates.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to ingest templates" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK] Templates ingested" -ForegroundColor Green
} else {
    Write-Host "`n[STEP 2] Skipping ingestion (--SkipIngest)" -ForegroundColor Gray
}

# Step 3: Run retrieval tests
Write-Host "`n[STEP 3] Running ChromaDB retrieval tests..." -ForegroundColor Yellow
python test_retrieval.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARN] Some retrieval tests failed" -ForegroundColor Yellow
}

if ($RetrievalOnly) {
    Write-Host "`n[DONE] Retrieval-only mode. Skipping API tests." -ForegroundColor Cyan
    exit 0
}

# Step 4: Start API (background)
$apiProcess = $null
if (-not $SkipAPI) {
    Write-Host "`n[STEP 4] Starting Generator API on port 8080..." -ForegroundColor Yellow

    # Check if API already running
    try {
        $apiCheck = Invoke-WebRequest -Uri "http://localhost:8080/" -TimeoutSec 3 -ErrorAction Stop
        Write-Host "  [OK] API already running" -ForegroundColor Green
    } catch {
        Write-Host "  Starting API server..." -ForegroundColor Gray
        $apiProcess = Start-Process -FilePath "python" -ArgumentList "generator_api.py" -PassThru -NoNewWindow -RedirectStandardOutput "test_output\api_stdout.log" -RedirectStandardError "test_output\api_stderr.log"
        Start-Sleep -Seconds 3

        # Verify API started
        try {
            $apiCheck = Invoke-WebRequest -Uri "http://localhost:8080/" -TimeoutSec 5 -ErrorAction Stop
            Write-Host "  [OK] API started (PID: $($apiProcess.Id))" -ForegroundColor Green
        } catch {
            Write-Host "  [ERROR] API failed to start. Check test_output\api_stderr.log" -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "`n[STEP 4] Skipping API start (--SkipAPI)" -ForegroundColor Gray
}

# Step 5: Run full test suite
Write-Host "`n[STEP 5] Running full test suite..." -ForegroundColor Yellow
python test_generator.py
$testResult = $LASTEXITCODE

# Step 6: Cleanup
if ($apiProcess -and -not $apiProcess.HasExited) {
    Write-Host "`n[STEP 6] Stopping API server..." -ForegroundColor Yellow
    Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] API stopped" -ForegroundColor Green
}

# Summary
Write-Host "`n" + "=" * 70 -ForegroundColor Cyan
if ($testResult -eq 0) {
    Write-Host "  ALL TESTS PASSED" -ForegroundColor Green
} else {
    Write-Host "  SOME TESTS FAILED - Check test_output\test_results.json" -ForegroundColor Red
}
Write-Host "=" * 70 -ForegroundColor Cyan

# Show output files
if (Test-Path "test_output") {
    Write-Host "`n  Generated files:" -ForegroundColor Gray
    Get-ChildItem -Path "test_output" -Recurse -File | ForEach-Object {
        Write-Host "    $($_.FullName) ($($_.Length) bytes)" -ForegroundColor Gray
    }
}

exit $testResult
