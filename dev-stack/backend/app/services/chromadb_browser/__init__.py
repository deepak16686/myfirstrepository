"""
File: __init__.py
Purpose: Package initializer for the ChromaDB Browser service. Exposes the ChromaDBBrowserService class and a singleton instance for browsing, inspecting, and deleting documents in ChromaDB collections.
When Used: Imported by the ChromaDB browser router to provide collection summary, detail, and document deletion endpoints to the frontend.
Why Created: Follows the singleton package pattern used throughout the services layer, giving the router a single import path to access ChromaDB browsing functionality.
"""
from app.services.chromadb_browser.service import ChromaDBBrowserService

chromadb_browser_service = ChromaDBBrowserService()

__all__ = ["ChromaDBBrowserService", "chromadb_browser_service"]
