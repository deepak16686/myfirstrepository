"""
Dependency Scanner Router

Endpoints for scanning Docker images for vulnerabilities via Trivy,
listing available images from Nexus, and viewing scan history.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.dependency_scanner import dependency_scanner_service

router = APIRouter(prefix="/dependency-scanner", tags=["Dependency Scanner"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    image: str
    severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
    ignore_unfixed: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/images")
async def list_images(repository: str = "docker-hosted"):
    """List Docker images available in Nexus for scanning."""
    try:
        result = await dependency_scanner_service.list_images(repository)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan")
async def scan_image(request: ScanRequest):
    """Scan a Docker image for vulnerabilities."""
    try:
        result = await dependency_scanner_service.scan_image(
            image=request.image,
            severity=request.severity,
            ignore_unfixed=request.ignore_unfixed,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Scan failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_history():
    """Get recent scan history (last 20 scans)."""
    return dependency_scanner_service.get_history()


@router.delete("/history")
async def clear_history():
    """Clear scan history."""
    return dependency_scanner_service.clear_history()
