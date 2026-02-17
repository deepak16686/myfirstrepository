"""Migration Assistant Service Package."""
from app.services.migration_assistant.service import MigrationAssistantService

migration_assistant_service = MigrationAssistantService()

__all__ = ["MigrationAssistantService", "migration_assistant_service"]
