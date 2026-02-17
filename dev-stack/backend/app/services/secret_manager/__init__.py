"""Secret Manager Service Package."""
from app.services.secret_manager.service import SecretManagerService

secret_manager_service = SecretManagerService()

__all__ = ["SecretManagerService", "secret_manager_service"]
