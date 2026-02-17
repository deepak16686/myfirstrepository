"""
ChromaDB Browser Service

Provides summary and detail views of ChromaDB collections and templates.
"""
from typing import Dict, Any, Optional

from app.config import tools_manager
from app.integrations.chromadb import ChromaDBIntegration


class ChromaDBBrowserService:
    """Service for browsing ChromaDB collections and templates."""

    def _get_integration(self) -> ChromaDBIntegration:
        """Create a ChromaDBIntegration instance from tools_manager config."""
        config = tools_manager.get_tool("chromadb")
        if not config:
            raise RuntimeError("ChromaDB is not configured")
        return ChromaDBIntegration(config)

    async def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all ChromaDB collections with counts and sample IDs."""
        integration = self._get_integration()
        try:
            collections_raw = await integration.list_collections()
            collections = []
            total_documents = 0

            for coll in collections_raw:
                name = coll.get("name", "unknown")
                coll_id = coll.get("id", "")

                count = await integration.get_collection_count(name)
                total_documents += count

                sample_ids = []
                sample_metadata = []
                if count > 0:
                    docs = await integration.get_documents(
                        collection_name=name,
                        limit=10,
                        include=["metadatas"],
                    )
                    sample_ids = docs.get("ids", [])[:10]
                    sample_metadata = docs.get("metadatas", [])[:10]

                collections.append({
                    "name": name,
                    "id": coll_id,
                    "count": count,
                    "sample_ids": sample_ids,
                    "sample_metadata": sample_metadata,
                })

            return {
                "success": True,
                "total_collections": len(collections),
                "total_documents": total_documents,
                "collections": collections,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await integration.close()

    async def get_collection_detail(
        self, collection_name: str, limit: int = 20, offset: int = 0
    ) -> Dict[str, Any]:
        """Get detailed documents from a specific collection."""
        integration = self._get_integration()
        try:
            count = await integration.get_collection_count(collection_name)
            docs = await integration.get_documents(
                collection_name=collection_name,
                limit=limit,
                offset=offset,
                include=["documents", "metadatas"],
            )
            return {
                "success": True,
                "collection": collection_name,
                "total": count,
                "limit": limit,
                "offset": offset,
                "ids": docs.get("ids", []),
                "documents": docs.get("documents", []),
                "metadatas": docs.get("metadatas", []),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await integration.close()

    async def delete_document(
        self, collection_name: str, document_id: str
    ) -> Dict[str, Any]:
        """Delete a single document from a collection by ID."""
        integration = self._get_integration()
        try:
            success = await integration.delete_documents(
                collection_name=collection_name,
                ids=[document_id],
            )
            return {
                "success": success,
                "message": f"Document '{document_id}' deleted from '{collection_name}'" if success else "Delete failed",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await integration.close()
