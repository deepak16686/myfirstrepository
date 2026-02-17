"""Release Notes Generator Service Package."""
from app.services.release_notes.service import ReleaseNotesService

release_notes_service = ReleaseNotesService()

__all__ = ["ReleaseNotesService", "release_notes_service"]
