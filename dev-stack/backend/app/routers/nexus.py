"""
File: nexus.py
Purpose: Exposes a comprehensive REST proxy to the Nexus Repository Manager API, covering
    repository management, component/asset CRUD, Docker image listing, scheduled tasks,
    blob stores, and user/role administration.
When Used: Invoked by the frontend Nexus tool card and by internal services (pipeline generators,
    dependency scanner) whenever artifact repository operations are needed via the /nexus/* routes.
Why Created: Wraps the NexusIntegration client into a FastAPI router with proper error handling
    and Pydantic response models, keeping Nexus-specific API logic out of higher-level services
    like the dependency scanner and pipeline image seeders.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.config import tools_manager
from app.integrations.nexus import NexusIntegration
from app.models.schemas import (
    NexusRepository, NexusComponent, NexusAsset, APIResponse
)

router = APIRouter(prefix="/nexus", tags=["Nexus Repository"])


def get_nexus() -> NexusIntegration:
    config = tools_manager.get_tool("nexus")
    if not config or not config.enabled:
        raise HTTPException(status_code=503, detail="Nexus integration not configured or disabled")
    return NexusIntegration(config)


# ============================================================================
# Repositories
# ============================================================================

@router.get("/repositories", response_model=List[NexusRepository])
async def list_repositories():
    """List all repositories"""
    nexus = get_nexus()
    try:
        return await nexus.list_repositories()
    finally:
        await nexus.close()


@router.get("/repositories/{name}", response_model=NexusRepository)
async def get_repository(name: str):
    """Get a specific repository"""
    nexus = get_nexus()
    try:
        repo = await nexus.get_repository(name)
        if not repo:
            raise HTTPException(status_code=404, detail=f"Repository '{name}' not found")
        return repo
    finally:
        await nexus.close()


@router.post("/repositories/docker", response_model=APIResponse)
async def create_docker_repository(
    name: str,
    http_port: int = 5000,
    https_port: Optional[int] = None,
    blob_store: str = "default"
):
    """Create a Docker hosted repository"""
    nexus = get_nexus()
    try:
        success = await nexus.create_docker_repository(name, http_port, https_port, blob_store)
        if success:
            return APIResponse(success=True, message=f"Docker repository '{name}' created")
        raise HTTPException(status_code=500, detail="Failed to create repository")
    finally:
        await nexus.close()


# ============================================================================
# Components
# ============================================================================

@router.get("/components")
async def search_components(
    repository: Optional[str] = None,
    name: Optional[str] = None,
    group: Optional[str] = None,
    version: Optional[str] = None,
    format: Optional[str] = None
):
    """Search for components"""
    nexus = get_nexus()
    try:
        return await nexus.search_components(repository, name, group, version, format)
    finally:
        await nexus.close()


@router.get("/components/{component_id}", response_model=NexusComponent)
async def get_component(component_id: str):
    """Get a specific component"""
    nexus = get_nexus()
    try:
        component = await nexus.get_component(component_id)
        if not component:
            raise HTTPException(status_code=404, detail=f"Component '{component_id}' not found")
        return component
    finally:
        await nexus.close()


@router.delete("/components/{component_id}", response_model=APIResponse)
async def delete_component(component_id: str):
    """Delete a component"""
    nexus = get_nexus()
    try:
        success = await nexus.delete_component(component_id)
        if success:
            return APIResponse(success=True, message="Component deleted")
        raise HTTPException(status_code=500, detail="Failed to delete component")
    finally:
        await nexus.close()


# ============================================================================
# Assets
# ============================================================================

@router.get("/assets")
async def list_assets(
    repository: str,
    continuation_token: Optional[str] = None
):
    """List assets in a repository"""
    nexus = get_nexus()
    try:
        return await nexus.list_assets(repository, continuation_token)
    finally:
        await nexus.close()


@router.get("/assets/{asset_id}", response_model=NexusAsset)
async def get_asset(asset_id: str):
    """Get a specific asset"""
    nexus = get_nexus()
    try:
        asset = await nexus.get_asset(asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
        return asset
    finally:
        await nexus.close()


@router.delete("/assets/{asset_id}", response_model=APIResponse)
async def delete_asset(asset_id: str):
    """Delete an asset"""
    nexus = get_nexus()
    try:
        success = await nexus.delete_asset(asset_id)
        if success:
            return APIResponse(success=True, message="Asset deleted")
        raise HTTPException(status_code=500, detail="Failed to delete asset")
    finally:
        await nexus.close()


# ============================================================================
# Docker-specific
# ============================================================================

@router.get("/docker/{repository}/images")
async def list_docker_images(repository: str):
    """List Docker images in a repository"""
    nexus = get_nexus()
    try:
        return await nexus.list_docker_images(repository)
    finally:
        await nexus.close()


@router.get("/docker/{repository}/images/{image_name}/tags")
async def get_docker_tags(repository: str, image_name: str):
    """Get tags for a Docker image"""
    nexus = get_nexus()
    try:
        tags = await nexus.get_docker_tags(repository, image_name)
        return {"image": image_name, "tags": tags}
    finally:
        await nexus.close()


# ============================================================================
# Tasks
# ============================================================================

@router.get("/tasks")
async def list_tasks():
    """List scheduled tasks"""
    nexus = get_nexus()
    try:
        return await nexus.list_tasks()
    finally:
        await nexus.close()


@router.post("/tasks/{task_id}/run", response_model=APIResponse)
async def run_task(task_id: str):
    """Run a scheduled task"""
    nexus = get_nexus()
    try:
        success = await nexus.run_task(task_id)
        if success:
            return APIResponse(success=True, message=f"Task '{task_id}' started")
        raise HTTPException(status_code=500, detail="Failed to start task")
    finally:
        await nexus.close()


# ============================================================================
# Blob Stores
# ============================================================================

@router.get("/blob-stores")
async def list_blob_stores():
    """List blob stores"""
    nexus = get_nexus()
    try:
        return await nexus.list_blob_stores()
    finally:
        await nexus.close()


@router.get("/blob-stores/{name}/quota")
async def get_blob_store_quota(name: str):
    """Get blob store quota status"""
    nexus = get_nexus()
    try:
        return await nexus.get_blob_store_quota(name)
    finally:
        await nexus.close()


# ============================================================================
# Security
# ============================================================================

@router.get("/users")
async def list_users():
    """List users"""
    nexus = get_nexus()
    try:
        return await nexus.list_users()
    finally:
        await nexus.close()


@router.get("/roles")
async def list_roles():
    """List roles"""
    nexus = get_nexus()
    try:
        return await nexus.list_roles()
    finally:
        await nexus.close()
