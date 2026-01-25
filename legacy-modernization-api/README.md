# Legacy Modernization Platform - FastAPI Service

AI-powered legacy application modernization REST API.

## Quick Start

1. Build and run:
```powershell
cd legacy-modernization-api
docker-compose up -d --build
```

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
```powershell
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration

Edit .env file to configure database, redis, and other service connections.
