"""
File: __init__.py
Purpose: Package initializer for the Migration Assistant service. Exposes the MigrationAssistantService class and a singleton instance for converting pipeline configurations between GitLab CI, Jenkins, and GitHub Actions formats.
When Used: Imported by the migration assistant router to provide pipeline format detection, conversion, and supported language listing endpoints to the frontend.
Why Created: Follows the singleton package pattern, providing a single import path for cross-format pipeline migration functionality.
"""
from app.services.migration_assistant.service import MigrationAssistantService

migration_assistant_service = MigrationAssistantService()

__all__ = ["MigrationAssistantService", "migration_assistant_service"]
