"""
ChromaDB Vector Database API Integration
"""
from typing import List, Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class ChromaDBIntegration(BaseIntegration):
    """ChromaDB vector database API integration"""

    def __init__(self, config: ToolConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "chromadb"

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/api/v1/heartbeat")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/api/v1/version")
            if response.status_code == 200:
                return response.text.strip('"')
        except Exception:
            pass
        return None

    # ========================================================================
    # Collections
    # ========================================================================

    async def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections"""
        response = await self.get("/api/v1/collections")
        response.raise_for_status()
        return response.json()

    async def create_collection(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new collection"""
        payload = {"name": name}
        if metadata:
            payload["metadata"] = metadata

        response = await self.post("/api/v1/collections", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_collection(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a collection by name"""
        response = await self.get(f"/api/v1/collections/{name}")
        if response.status_code == 200:
            return response.json()
        return None

    async def delete_collection(self, name: str) -> bool:
        """Delete a collection"""
        response = await self.delete(f"/api/v1/collections/{name}")
        return response.status_code == 200

    async def get_collection_count(self, collection_id: str) -> int:
        """Get the number of items in a collection"""
        response = await self.get(f"/api/v1/collections/{collection_id}/count")
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Documents
    # ========================================================================

    async def add_documents(
        self,
        collection_id: str,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Add documents to a collection"""
        payload = {"ids": ids}
        if documents:
            payload["documents"] = documents
        if embeddings:
            payload["embeddings"] = embeddings
        if metadatas:
            payload["metadatas"] = metadatas

        response = await self.post(f"/api/v1/collections/{collection_id}/add", json=payload)
        return response.status_code == 201

    async def get_documents(
        self,
        collection_id: str,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        include: List[str] = None
    ) -> Dict[str, Any]:
        """Get documents from a collection"""
        payload = {
            "limit": limit,
            "offset": offset
        }
        if ids:
            payload["ids"] = ids
        if where:
            payload["where"] = where
        if include:
            payload["include"] = include
        else:
            payload["include"] = ["documents", "metadatas"]

        response = await self.post(f"/api/v1/collections/{collection_id}/get", json=payload)
        response.raise_for_status()
        return response.json()

    async def update_documents(
        self,
        collection_id: str,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Update documents in a collection"""
        payload = {"ids": ids}
        if documents:
            payload["documents"] = documents
        if embeddings:
            payload["embeddings"] = embeddings
        if metadatas:
            payload["metadatas"] = metadatas

        response = await self.post(f"/api/v1/collections/{collection_id}/update", json=payload)
        return response.status_code == 200

    async def delete_documents(
        self,
        collection_id: str,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Delete documents from a collection"""
        payload = {}
        if ids:
            payload["ids"] = ids
        if where:
            payload["where"] = where

        response = await self.post(f"/api/v1/collections/{collection_id}/delete", json=payload)
        return response.status_code == 200

    # ========================================================================
    # Query / Search
    # ========================================================================

    async def query(
        self,
        collection_id: str,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        include: List[str] = None
    ) -> Dict[str, Any]:
        """Query/search a collection"""
        payload = {"n_results": n_results}
        if query_texts:
            payload["query_texts"] = query_texts
        if query_embeddings:
            payload["query_embeddings"] = query_embeddings
        if where:
            payload["where"] = where
        if include:
            payload["include"] = include
        else:
            payload["include"] = ["documents", "metadatas", "distances"]

        response = await self.post(f"/api/v1/collections/{collection_id}/query", json=payload)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Utilities
    # ========================================================================

    async def reset(self) -> bool:
        """Reset the database (delete all collections)"""
        response = await self.post("/api/v1/reset")
        return response.status_code == 200
