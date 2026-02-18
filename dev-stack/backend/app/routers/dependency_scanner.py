"""
File: dependency_scanner.py
Purpose: Provides a streamlined interface for scanning Docker images from Nexus for vulnerabilities
    via Trivy, listing available images in a Nexus repository, and maintaining an in-memory scan
    history of recent results.
When Used: Invoked by the frontend Dependency Scanner tool card when a user selects an image from
    the Nexus image list and triggers a vulnerability scan, or reviews/clears scan history via
    the /dependency-scanner/* routes.
Why Created: Wraps the lower-level Trivy and Nexus integrations into a higher-level scanning
    workflow with scan history tracking, providing a simpler API surface than the raw Trivy
    router for the common use case of scanning Nexus-hosted Docker images.
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
