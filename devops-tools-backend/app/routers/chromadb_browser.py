"""
ChromaDB Browser Router

Endpoints for browsing ChromaDB collections, templates, and documents.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.chromadb_browser import chromadb_browser_service

router = APIRouter(prefix="/chromadb-browser", tags=["ChromaDB Browser"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CollectionDetailQuery(BaseModel):
    collection_name: str
    limit: int = 20
    offset: int = 0


class DeleteDocumentRequest(BaseModel):
    collection_name: str
    document_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/summary")
async def get_summary():
    """Get summary of all ChromaDB collections with counts and sample IDs."""
    try:
        result = await chromadb_browser_service.get_summary()
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collection")
async def get_collection_detail(query: CollectionDetailQuery):
    """Get documents from a specific ChromaDB collection."""
    try:
        result = await chromadb_browser_service.get_collection_detail(
            collection_name=query.collection_name,
            limit=query.limit,
            offset=query.offset,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
async def delete_document(request: DeleteDocumentRequest):
    """Delete a document from a ChromaDB collection."""
    try:
        result = await chromadb_browser_service.delete_document(
            collection_name=request.collection_name,
            document_id=request.document_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
