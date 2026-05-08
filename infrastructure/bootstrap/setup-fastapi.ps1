# Legacy Modernization Platform - FastAPI Setup Script
# Creates complete directory structure and all required files

# Set base directory
$baseDir = "legacy-modernization-api"

Write-Host "Creating Legacy Modernization API structure..." -ForegroundColor Green

# Create directory structure
$directories = @(
    "$baseDir",
    "$baseDir/app",
    "$baseDir/app/models",
    "$baseDir/app/routers",
    "$baseDir/app/services"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created directory: $dir" -ForegroundColor Cyan
    }
}

# Create __init__.py files
$initFiles = @(
    "$baseDir/app/__init__.py",
    "$baseDir/app/models/__init__.py",
    "$baseDir/app/routers/__init__.py",
    "$baseDir/app/services/__init__.py"
)

foreach ($file in $initFiles) {
    New-Item -ItemType File -Path $file -Force | Out-Null
    Write-Host "Created file: $file" -ForegroundColor Yellow
}

# Create requirements.txt
$requirementsTxt = @"
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
redis==5.0.1
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.26.0
"@
Set-Content -Path "$baseDir/requirements.txt" -Value $requirementsTxt
Write-Host "Created: requirements.txt" -ForegroundColor Yellow

# Create .env template
$envTemplate = @"
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/modernization

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# Ollama Configuration
OLLAMA_URL=http://ollama:11434

# MinIO Configuration
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# ChromaDB Configuration
CHROMADB_URL=http://chromadb:8000

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
"@
Set-Content -Path "$baseDir/.env" -Value $envTemplate
Write-Host "Created: .env" -ForegroundColor Yellow

# Create app/config.py
$configPy = @"
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@postgres:5432/modernization"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    
    # Ollama
    OLLAMA_URL: str = "http://ollama:11434"
    
    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    
    # ChromaDB
    CHROMADB_URL: str = "http://chromadb:8000"
    
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 4
    
    class Config:
        env_file = ".env"

settings = Settings()
"@
Set-Content -Path "$baseDir/app/config.py" -Value $configPy
Write-Host "Created: app/config.py" -ForegroundColor Yellow

# Create app/main.py
$mainPy = @"
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health, analysis
from app.config import settings

app = FastAPI(
    title="Legacy Modernization Platform API",
    description="AI-powered legacy application modernization",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])

@app.get("/")
async def root():
    return {
        "message": "Legacy Modernization Platform API",
        "version": "1.0.0",
        "status": "running"
    }
"@
Set-Content -Path "$baseDir/app/main.py" -Value $mainPy
Write-Host "Created: app/main.py" -ForegroundColor Yellow

# Create app/routers/health.py
$healthPy = @"
from fastapi import APIRouter, status
from datetime import datetime
import psutil
import platform

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "api",
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "platform": platform.system()
        }
    }

@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """Readiness probe for Kubernetes/container orchestration"""
    # TODO: Add checks for database, redis, ollama connectivity
    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """Liveness probe for Kubernetes/container orchestration"""
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat()
    }
"@
Set-Content -Path "$baseDir/app/routers/health.py" -Value $healthPy
Write-Host "Created: app/routers/health.py" -ForegroundColor Yellow

# Create app/routers/analysis.py
$analysisPy = @"
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime
import uuid

router = APIRouter()

class AnalysisRequest(BaseModel):
    repository_url: HttpUrl
    branch: str = "main"
    analysis_type: str = "full"  # full, security, performance, architecture

class AnalysisResponse(BaseModel):
    job_id: str
    status: str
    repository: str
    branch: str
    created_at: str
    message: str

@router.post("/analysis/start", response_model=AnalysisResponse)
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Initiate legacy code analysis workflow"""
    job_id = str(uuid.uuid4())
    
    # TODO: Add background task to process analysis
    # background_tasks.add_task(process_analysis, job_id, request)
    
    return AnalysisResponse(
        job_id=job_id,
        status="initiated",
        repository=str(request.repository_url),
        branch=request.branch,
        created_at=datetime.utcnow().isoformat(),
        message="Analysis job created successfully"
    )

@router.get("/analysis/{job_id}")
async def get_analysis_status(job_id: str):
    """Get status of analysis job"""
    # TODO: Implement job status retrieval from database
    return {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Job status retrieval - implementation pending"
    }

@router.get("/analysis")
async def list_analyses(skip: int = 0, limit: int = 10):
    """List all analysis jobs"""
    # TODO: Implement pagination and database query
    return {
        "total": 0,
        "skip": skip,
        "limit": limit,
        "items": []
    }
"@
Set-Content -Path "$baseDir/app/routers/analysis.py" -Value $analysisPy
Write-Host "Created: app/routers/analysis.py" -ForegroundColor Yellow

# Create Dockerfile
$dockerfile = @"
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY .env .env

# Create non-root user
RUN useradd -m -u 1000 apiuser && chown -R apiuser:apiuser /app
USER apiuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/v1/health')"

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
"@
Set-Content -Path "$baseDir/Dockerfile" -Value $dockerfile
Write-Host "Created: Dockerfile" -ForegroundColor Yellow

# Create docker-compose.yml
$dockerCompose = @"
version: '3.8'

services:
  fastapi:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: modernization-api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/modernization
      - REDIS_URL=redis://redis:6379/0
      - OLLAMA_URL=http://ollama:11434
      - MINIO_ENDPOINT=minio:9000
      - CHROMADB_URL=http://chromadb:8000
    volumes:
      - ./app:/app/app
      - ./logs:/app/logs
    networks:
      - modernization-network
    restart: unless-stopped
    depends_on:
      - postgres
      - redis
      - ollama
      - minio
      - chromadb
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  modernization-network:
    external: true

"@
Set-Content -Path "$baseDir/docker-compose.yml" -Value $dockerCompose
Write-Host "Created: docker-compose.yml" -ForegroundColor Yellow

# Create .dockerignore
$dockerignore = @"
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
pip-log.txt
pip-delete-this-directory.txt
.git
.gitignore
README.md
.env.example
*.md
.vscode
.idea
*.log
"@
Set-Content -Path "$baseDir/.dockerignore" -Value $dockerignore
Write-Host "Created: .dockerignore" -ForegroundColor Yellow

# Create README.md
$readme = @"
# Legacy Modernization Platform - FastAPI Service

AI-powered legacy application modernization REST API.

## Quick Start

1. Build and run:
``````powershell
cd legacy-modernization-api
docker-compose up -d --build
``````

2. Access API:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc
   - Health Check: http://localhost:8000/api/v1/health

## API Endpoints

### Health Endpoints
- GET /api/v1/health - Health check
- GET /api/v1/health/ready - Readiness probe
- GET /api/v1/health/live - Liveness probe

### Analysis Endpoints
- POST /api/v1/analysis/start - Start analysis job
- GET /api/v1/analysis/{job_id} - Get job status
- GET /api/v1/analysis - List all analyses

## Development
``````powershell
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
``````

## Configuration

Edit .env file to configure database, redis, and other service connections.
"@
Set-Content -Path "$baseDir/README.md" -Value $readme
Write-Host "Created: README.md" -ForegroundColor Yellow

# Update requirements.txt to include psutil
$updatedRequirements = @"
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
redis==5.0.1
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.26.0
psutil==5.9.8
"@
Set-Content -Path "$baseDir/requirements.txt" -Value $updatedRequirements

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "FastAPI structure created successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "`nDirectory: $baseDir" -ForegroundColor Cyan
Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. cd $baseDir" -ForegroundColor White
Write-Host "2. docker-compose up -d --build" -ForegroundColor White
Write-Host "3. Visit http://localhost:8000/docs" -ForegroundColor White
Write-Host "`n========================================`n" -ForegroundColor Green