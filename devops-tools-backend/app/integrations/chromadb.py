"""
ChromaDB Vector Database API Integration (v2 API)
"""
from typing import List, Optional, Dict, Any
from app.integrations.base import BaseIntegration
from app.config import ToolConfig
from app.models.schemas import ToolStatus


class ChromaDBIntegration(BaseIntegration):
    """ChromaDB vector database API integration using v2 API"""

    # Default tenant and database for ChromaDB v2
    DEFAULT_TENANT = "default_tenant"
    DEFAULT_DATABASE = "default_database"

    def __init__(self, config: ToolConfig, tenant: str = None, database: str = None):
        super().__init__(config)
        self.tenant = tenant or self.DEFAULT_TENANT
        self.database = database or self.DEFAULT_DATABASE
        self._collection_uuid_cache: Dict[str, str] = {}

    @property
    def name(self) -> str:
        return "chromadb"

    def _base_path(self) -> str:
        """Build the base path for database operations"""
        return f"/api/v2/tenants/{self.tenant}/databases/{self.database}"

    def _collection_path(self, collection_uuid: str = "") -> str:
        """Build the path for collection operations using UUID"""
        base = f"{self._base_path()}/collections"
        if collection_uuid:
            return f"{base}/{collection_uuid}"
        return base

    async def _get_collection_uuid(self, name: str) -> Optional[str]:
        """Get collection UUID by name (with caching)"""
        if name in self._collection_uuid_cache:
            return self._collection_uuid_cache[name]

        # List all collections and find by name
        collections = await self.list_collections()
        for coll in collections:
            if coll.get('name') == name:
                uuid = coll.get('id')
                self._collection_uuid_cache[name] = uuid
                return uuid
        return None

    async def health_check(self) -> ToolStatus:
        try:
            response = await self.get("/api/v2/heartbeat")
            if response.status_code == 200:
                return ToolStatus.HEALTHY
            return ToolStatus.UNHEALTHY
        except Exception:
            return ToolStatus.UNHEALTHY

    async def get_version(self) -> Optional[str]:
        try:
            response = await self.get("/api/v2/healthcheck")
            if response.status_code == 200:
                return "v2"
        except Exception:
            pass
        return None

    # ========================================================================
    # Collections
    # ========================================================================

    async def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections"""
        response = await self.get(f"{self._base_path()}/collections")
        response.raise_for_status()
        return response.json()

    async def create_collection(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new collection. Returns existing collection if already exists."""
        payload = {"name": name}
        if metadata:
            payload["metadata"] = metadata

        response = await self.post(f"{self._base_path()}/collections", json=payload)

        # Handle 409 Conflict - collection already exists
        if response.status_code == 409:
            # Get the existing collection instead
            existing = await self.get_collection(name)
            if existing:
                return existing
            # If we can't get it, return empty dict to indicate partial success
            return {"name": name, "exists": True}

        response.raise_for_status()
        result = response.json()
        # Cache the UUID
        if result.get('id'):
            self._collection_uuid_cache[name] = result['id']
        return result

    async def get_collection(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a collection by name"""
        uuid = await self._get_collection_uuid(name)
        if not uuid:
            return None
        response = await self.get(self._collection_path(uuid))
        if response.status_code == 200:
            return response.json()
        return None

    async def delete_collection(self, name: str) -> bool:
        """Delete a collection by name"""
        uuid = await self._get_collection_uuid(name)
        if not uuid:
            return False
        response = await self.delete(self._collection_path(uuid))
        if name in self._collection_uuid_cache:
            del self._collection_uuid_cache[name]
        return response.status_code in [200, 204]

    async def get_collection_count(self, collection_name: str) -> int:
        """Get the number of items in a collection"""
        uuid = await self._get_collection_uuid(collection_name)
        if not uuid:
            return 0
        response = await self.get(f"{self._collection_path(uuid)}/count")
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Documents
    # ========================================================================

    async def add_documents(
        self,
        collection_name: str,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Add documents to a collection.

        Note: ChromaDB v2 requires embeddings. If not provided, dummy embeddings
        are generated for metadata-only storage use cases.
        """
        uuid = await self._get_collection_uuid(collection_name)
        if not uuid:
            print(f"[ChromaDB] Collection not found: {collection_name}")
            return False

        payload = {"ids": ids}
        if documents:
            payload["documents"] = documents

        # ChromaDB v2 requires embeddings - provide dummy embeddings if not specified
        if embeddings:
            payload["embeddings"] = embeddings
        elif documents:
            # Generate simple hash-based embeddings for metadata-only queries
            # This is a workaround for ChromaDB v2's embedding requirement
            import hashlib
            dummy_embeddings = []
            for doc in documents:
                # Create a simple 384-dim embedding from document hash
                doc_hash = hashlib.sha384(doc.encode()).digest()
                embedding = [float(b) / 255.0 for b in doc_hash]
                dummy_embeddings.append(embedding)
            payload["embeddings"] = dummy_embeddings

        if metadatas:
            payload["metadatas"] = metadatas

        response = await self.post(f"{self._collection_path(uuid)}/add", json=payload)
        if response.status_code not in [200, 201]:
            print(f"[ChromaDB] Add documents failed: {response.status_code} - {response.text[:200]}")
        return response.status_code in [200, 201]

    async def get_documents(
        self,
        collection_name: str,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        include: List[str] = None
    ) -> Dict[str, Any]:
        """Get documents from a collection using metadata filter"""
        uuid = await self._get_collection_uuid(collection_name)
        if not uuid:
            return {"ids": [], "documents": [], "metadatas": []}

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

        response = await self.post(f"{self._collection_path(uuid)}/get", json=payload)
        response.raise_for_status()
        return response.json()

    async def update_documents(
        self,
        collection_name: str,
        ids: List[str],
        documents: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Update documents in a collection"""
        uuid = await self._get_collection_uuid(collection_name)
        if not uuid:
            return False

        payload = {"ids": ids}
        if documents:
            payload["documents"] = documents

        # ChromaDB v2 requires embeddings - provide dummy embeddings if not specified
        if embeddings:
            payload["embeddings"] = embeddings
        elif documents:
            import hashlib
            dummy_embeddings = []
            for doc in documents:
                doc_hash = hashlib.sha384(doc.encode()).digest()
                embedding = [float(b) / 255.0 for b in doc_hash]
                dummy_embeddings.append(embedding)
            payload["embeddings"] = dummy_embeddings
        if metadatas:
            payload["metadatas"] = metadatas

        response = await self.post(f"{self._collection_path(uuid)}/update", json=payload)
        return response.status_code == 200

    async def delete_documents(
        self,
        collection_name: str,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Delete documents from a collection"""
        uuid = await self._get_collection_uuid(collection_name)
        if not uuid:
            return False

        payload = {}
        if ids:
            payload["ids"] = ids
        if where:
            payload["where"] = where

        response = await self.post(f"{self._collection_path(uuid)}/delete", json=payload)
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
        """
        Query/search a collection.
        NOTE: ChromaDB v2 requires embeddings for vector search.
        For metadata-based filtering, use get_documents with where filter instead.
        """
        uuid = await self._get_collection_uuid(collection_id)
        if not uuid:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]]}

        # If no embeddings provided, fall back to get_documents with where filter
        if not query_embeddings:
            print(f"[ChromaDB] No embeddings provided, using get_documents instead")
            result = await self.get_documents(
                collection_name=collection_id,
                where=where,
                limit=n_results,
                include=include or ["documents", "metadatas"]
            )
            # Convert get format to query format (wrap in lists)
            return {
                "ids": [result.get("ids", [])],
                "documents": [result.get("documents", [])],
                "metadatas": [result.get("metadatas", [])]
            }

        payload = {"n_results": n_results}
        if query_embeddings:
            payload["query_embeddings"] = query_embeddings
        if where:
            payload["where"] = where
        if include:
            payload["include"] = include
        else:
            payload["include"] = ["documents", "metadatas", "distances"]

        response = await self.post(f"{self._collection_path(uuid)}/query", json=payload)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # Utilities
    # ========================================================================

    async def reset(self) -> bool:
        """Reset the database (delete all collections)"""
        response = await self.post("/api/v2/reset")
        self._collection_uuid_cache.clear()
        return response.status_code == 200
