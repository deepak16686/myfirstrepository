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
