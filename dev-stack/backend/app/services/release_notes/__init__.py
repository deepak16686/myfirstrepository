"""
File: __init__.py
Purpose: Package initializer for the Release Notes Generator service. Exposes the ReleaseNotesService class and a singleton instance for generating formatted release notes from git commit history using an LLM.
When Used: Imported by the release notes router to provide the release notes generation endpoint to the frontend.
Why Created: Follows the singleton package pattern, providing a single import path for LLM-powered release notes generation with multiple output format options.
"""
from app.services.release_notes.service import ReleaseNotesService

release_notes_service = ReleaseNotesService()

__all__ = ["ReleaseNotesService", "release_notes_service"]
