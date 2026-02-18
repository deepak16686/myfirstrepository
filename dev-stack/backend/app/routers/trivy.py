"""
File: trivy.py
Purpose: Exposes a comprehensive REST proxy to the Trivy security scanner, supporting container
    image scanning, git repository scanning, filesystem scanning, configuration misconfiguration
    detection, SBOM generation, and license scanning.
When Used: Invoked by the frontend Trivy tool card for on-demand security scans, and consumed
    internally by the dependency scanner and compliance checker services for automated
    vulnerability assessments via the /trivy/* routes.
Why Created: Wraps the TrivyIntegration client into a FastAPI router covering all Trivy scan
    modes (image, repo, filesystem, config, SBOM, licenses), keeping raw Trivy API details
    separate from the higher-level dependency scanner and compliance checker workflows.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any

from app.config import tools_manager
from app.integrations.trivy import TrivyIntegration
from app.models.schemas import TrivyScanRequest, TrivyScanResult, APIResponse

router = APIRouter(prefix="/trivy", tags=["Trivy Security"])


def get_trivy() -> TrivyIntegration:
    config = tools_manager.get_tool("trivy")
    if not config or not config.enabled:
        raise HTTPException(status_code=503, detail="Trivy integration not configured or disabled")
    return TrivyIntegration(config)


# ============================================================================
# Health & Status
# ============================================================================

@router.get("/status")
async def get_status():
    """Get Trivy server status"""
    trivy = get_trivy()
    try:
        status = await trivy.health_check()
        version = await trivy.get_version()
        db_status = await trivy.get_db_status()
        return {
            "status": status,
            "version": version,
            "database": db_status
        }
    finally:
        await trivy.close()


@router.post("/db/update", response_model=APIResponse)
async def update_database():
    """Trigger vulnerability database update"""
    trivy = get_trivy()
    try:
        success = await trivy.update_db()
        if success:
            return APIResponse(success=True, message="Database update triggered")
        return APIResponse(success=False, message="Failed to trigger database update")
    finally:
        await trivy.close()


# ============================================================================
# Image Scanning
# ============================================================================

@router.post("/scan/image", response_model=TrivyScanResult)
async def scan_image(request: TrivyScanRequest):
    """
    Scan a container image for vulnerabilities.

    Args:
        image: Container image to scan (e.g., "nginx:latest", "python:3.11")
        severity: Comma-separated severity levels (UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL)
        ignore_unfixed: Skip vulnerabilities without fixes
    """
    trivy = get_trivy()
    try:
        return await trivy.scan_image(
            request.image,
            request.severity,
            request.ignore_unfixed
        )
    finally:
        await trivy.close()


@router.get("/scan/image/{image:path}", response_model=TrivyScanResult)
async def scan_image_get(
    image: str,
    severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL",
    ignore_unfixed: bool = False
):
    """
    Scan a container image for vulnerabilities (GET method for convenience).

    Example: /trivy/scan/image/nginx:latest
    """
    trivy = get_trivy()
    try:
        return await trivy.scan_image(image, severity, ignore_unfixed)
    finally:
        await trivy.close()


# ============================================================================
# Repository Scanning
# ============================================================================

@router.post("/scan/repo")
async def scan_repository(
    repo_url: str,
    branch: str = "main",
    severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
):
    """
    Scan a git repository for vulnerabilities.

    Args:
        repo_url: Git repository URL
        branch: Branch to scan
        severity: Comma-separated severity levels
    """
    trivy = get_trivy()
    try:
        return await trivy.scan_repo(repo_url, branch, severity)
    finally:
        await trivy.close()


# ============================================================================
# Filesystem Scanning
# ============================================================================

@router.post("/scan/fs")
async def scan_filesystem(
    path: str,
    severity: str = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
):
    """
    Scan a filesystem path for vulnerabilities.

    Args:
        path: Path to scan
        severity: Comma-separated severity levels
    """
    trivy = get_trivy()
    try:
        return await trivy.scan_filesystem(path, severity)
    finally:
        await trivy.close()


# ============================================================================
# Configuration Scanning
# ============================================================================

@router.post("/scan/config")
async def scan_configuration(
    config_type: str,
    content: str
):
    """
    Scan configuration files for misconfigurations.

    Args:
        config_type: Type of config (dockerfile, kubernetes, terraform, cloudformation)
        content: Configuration content to scan
    """
    trivy = get_trivy()
    try:
        return await trivy.scan_config(config_type, content)
    finally:
        await trivy.close()


# ============================================================================
# SBOM
# ============================================================================

@router.get("/sbom/{image:path}")
async def generate_sbom(
    image: str,
    format: str = "cyclonedx"
):
    """
    Generate Software Bill of Materials (SBOM) for an image.

    Args:
        image: Container image
        format: SBOM format (cyclonedx, spdx, spdx-json)
    """
    trivy = get_trivy()
    try:
        return await trivy.generate_sbom(image, format)
    finally:
        await trivy.close()


# ============================================================================
# License Scanning
# ============================================================================

@router.get("/licenses/{image:path}")
async def scan_licenses(image: str):
    """Scan for license information in a container image"""
    trivy = get_trivy()
    try:
        return await trivy.scan_licenses(image)
    finally:
        await trivy.close()
