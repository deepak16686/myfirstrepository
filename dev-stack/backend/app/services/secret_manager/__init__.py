"""
File: __init__.py
Purpose: Package initializer for the Secret Manager service. Exposes the SecretManagerService class and a singleton instance for unified secret management across GitLab, Gitea, and Jenkins.
When Used: Imported by the secret manager router to provide CRUD endpoints for CI/CD secrets across all three git/CI platforms.
Why Created: Follows the singleton package pattern, providing a single import path for cross-platform secret management that abstracts away the different APIs of GitLab, Gitea, and Jenkins.
"""
from app.services.secret_manager.service import SecretManagerService

secret_manager_service = SecretManagerService()

__all__ = ["SecretManagerService", "secret_manager_service"]
