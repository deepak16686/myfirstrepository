"""
File: nexus.py
Purpose: Nexus Repository Manager REST API client for managing repositories, Docker images, components,
         assets, blob stores, security, and scheduled tasks. Provides the Docker V2 search surface
         needed for image existence checks during pipeline validation.
When Used: Called by pipeline image_seeder modules (to check if Docker images exist in Nexus), by LLM
           fixers (to list available images for error correction), by the nexus router (REST proxy),
           and by the dependency_scanner for on-demand scanning.
Why Created: Centralizes all Nexus API interactions so pipeline generators can verify images exist in
             the private registry (localhost:5001) before committing pipelines.
"""
from typing import List, Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import (
    ToolStatus, NexusRepository, NexusComponent, NexusAsset
)


class NexusIntegration(BaseIntegration):
    """Nexus Repository Manager API integration"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "nexus"

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/service/rest/v1/status")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/service/rest/v1/status")
            if response.status_code == 200:
                data = response.json()
                return data.get("version")
        except Exception:
            pass
        return None

    # ========================================================================
    # Repositories
    # ========================================================================

    async def list_repositories(self) -> List[NexusRepository]:
        """List all repositories"""
        response = await self.get("/service/rest/v1/repositories")
        response.raise_for_status()
        repos = []
        for repo in response.json():
            repos.append(NexusRepository(
                name=repo.get("name"),
                format=repo.get("format"),
                type=repo.get("type"),
                url=repo.get("url"),
                online=repo.get("online", True)
            ))
        return repos

    async def get_repository(self, name: str) -> Optional[NexusRepository]:
        """Get a specific repository"""
        response = await self.get(f"/service/rest/v1/repositories/{name}")
        if response.status_code == 200:
            repo = response.json()
            return NexusRepository(
                name=repo.get("name"),
                format=repo.get("format"),
                type=repo.get("type"),
                url=repo.get("url"),
                online=repo.get("online", True)
            )
        return None

    async def create_docker_repository(
        self,
        name: str,
        http_port: int = 5000,
        https_port: Optional[int] = None,
        blob_store: str = "default"
    ) -> bool:
        """Create a Docker hosted repository"""
        payload = {
            "name": name,
            "online": True,
            "storage": {
                "blobStoreName": blob_store,
                "strictContentTypeValidation": True,
                "writePolicy": "ALLOW"
            },
            "docker": {
                "v1Enabled": False,
                "forceBasicAuth": True,
                "httpPort": http_port
            }
        }
        if https_port:
            payload["docker"]["httpsPort"] = https_port

        response = await self.post("/service/rest/v1/repositories/docker/hosted", json=payload)
        return response.status_code == 201

    # ========================================================================
    # Components
    # ========================================================================

    async def search_components(
        self,
        repository: Optional[str] = None,
        name: Optional[str] = None,
        group: Optional[str] = None,
        version: Optional[str] = None,
        format: Optional[str] = None
    ) -> List[NexusComponent]:
        """Search for components"""
        params = {}
        if repository:
            params["repository"] = repository
        if name:
            params["name"] = name
        if group:
            params["group"] = group
        if version:
            params["version"] = version
        if format:
            params["format"] = format

        response = await self.get("/service/rest/v1/search", params=params)
        response.raise_for_status()
        data = response.json()

        components = []
        for item in data.get("items", []):
            components.append(NexusComponent(
                id=item.get("id"),
                repository=item.get("repository"),
                format=item.get("format"),
                group=item.get("group"),
                name=item.get("name"),
                version=item.get("version")
            ))
        return components

    async def get_component(self, component_id: str) -> Optional[NexusComponent]:
        """Get a specific component"""
        response = await self.get(f"/service/rest/v1/components/{component_id}")
        if response.status_code == 200:
            item = response.json()
            return NexusComponent(
                id=item.get("id"),
                repository=item.get("repository"),
                format=item.get("format"),
                group=item.get("group"),
                name=item.get("name"),
                version=item.get("version")
            )
        return None

    async def delete_component(self, component_id: str) -> bool:
        """Delete a component"""
        response = await self.delete(f"/service/rest/v1/components/{component_id}")
        return response.status_code == 204

    # ========================================================================
    # Assets
    # ========================================================================

    async def list_assets(
        self,
        repository: str,
        continuation_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List assets in a repository"""
        params = {"repository": repository}
        if continuation_token:
            params["continuationToken"] = continuation_token

        response = await self.get("/service/rest/v1/assets", params=params)
        response.raise_for_status()
        data = response.json()

        assets = []
        for item in data.get("items", []):
            assets.append(NexusAsset(
                id=item.get("id"),
                path=item.get("path"),
                download_url=item.get("downloadUrl"),
                format=item.get("format"),
                content_type=item.get("contentType")
            ))

        return {
            "assets": assets,
            "continuation_token": data.get("continuationToken")
        }

    async def get_asset(self, asset_id: str) -> Optional[NexusAsset]:
        """Get a specific asset"""
        response = await self.get(f"/service/rest/v1/assets/{asset_id}")
        if response.status_code == 200:
            item = response.json()
            return NexusAsset(
                id=item.get("id"),
                path=item.get("path"),
                download_url=item.get("downloadUrl"),
                format=item.get("format"),
                content_type=item.get("contentType")
            )
        return None

    async def delete_asset(self, asset_id: str) -> bool:
        """Delete an asset"""
        response = await self.delete(f"/service/rest/v1/assets/{asset_id}")
        return response.status_code == 204

    # ========================================================================
    # Docker-specific
    # ========================================================================

    async def list_docker_images(self, repository: str) -> List[Dict[str, Any]]:
        """List Docker images in a repository"""
        params = {"repository": repository, "format": "docker"}
        response = await self.get("/service/rest/v1/search", params=params)
        response.raise_for_status()
        data = response.json()

        images = []
        for item in data.get("items", []):
            images.append({
                "name": item.get("name"),
                "version": item.get("version"),
                "repository": item.get("repository"),
                "id": item.get("id")
            })
        return images

    async def get_docker_tags(self, repository: str, image_name: str) -> List[str]:
        """Get tags for a Docker image"""
        params = {
            "repository": repository,
            "format": "docker",
            "name": image_name
        }
        response = await self.get("/service/rest/v1/search", params=params)
        response.raise_for_status()
        data = response.json()

        tags = set()
        for item in data.get("items", []):
            if item.get("version"):
                tags.add(item.get("version"))
        return list(tags)

    # ========================================================================
    # Tasks
    # ========================================================================

    async def list_tasks(self) -> List[Dict[str, Any]]:
        """List scheduled tasks"""
        response = await self.get("/service/rest/v1/tasks")
        response.raise_for_status()
        return response.json().get("items", [])

    async def run_task(self, task_id: str) -> bool:
        """Run a scheduled task"""
        response = await self.post(f"/service/rest/v1/tasks/{task_id}/run")
        return response.status_code == 204

    # ========================================================================
    # Blob Stores
    # ========================================================================

    async def list_blob_stores(self) -> List[Dict[str, Any]]:
        """List blob stores"""
        response = await self.get("/service/rest/v1/blobstores")
        response.raise_for_status()
        return response.json()

    async def get_blob_store_quota(self, name: str) -> Dict[str, Any]:
        """Get blob store quota status"""
        response = await self.get(f"/service/rest/v1/blobstores/{name}/quota-status")
        if response.status_code == 200:
            return response.json()
        return {}

    # ========================================================================
    # Security
    # ========================================================================

    async def list_users(self) -> List[Dict[str, Any]]:
        """List users"""
        response = await self.get("/service/rest/v1/security/users")
        response.raise_for_status()
        return response.json()

    async def list_roles(self) -> List[Dict[str, Any]]:
        """List roles"""
        response = await self.get("/service/rest/v1/security/roles")
        response.raise_for_status()
        return response.json()
