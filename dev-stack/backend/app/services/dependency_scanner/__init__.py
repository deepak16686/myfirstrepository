"""Dependency Scanner Service Package."""
from app.services.dependency_scanner.service import DependencyScannerService

dependency_scanner_service = DependencyScannerService()

__all__ = ["DependencyScannerService", "dependency_scanner_service"]
