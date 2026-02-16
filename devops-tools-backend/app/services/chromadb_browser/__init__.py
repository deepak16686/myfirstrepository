"""ChromaDB Browser Service Package."""
from app.services.chromadb_browser.service import ChromaDBBrowserService

chromadb_browser_service = ChromaDBBrowserService()

__all__ = ["ChromaDBBrowserService", "chromadb_browser_service"]
