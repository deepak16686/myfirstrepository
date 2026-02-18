"""
File: __init__.py
Purpose: Package initializer for the Dependency Scanner service. Exposes the DependencyScannerService class and a singleton instance for scanning Docker images for vulnerabilities using Trivy.
When Used: Imported by the dependency scanner router to provide image listing, vulnerability scanning, and scan history endpoints to the frontend.
Why Created: Follows the singleton package pattern, providing a single import path for Trivy-based container image vulnerability scanning with Nexus registry integration.
"""
from app.services.dependency_scanner.service import DependencyScannerService

dependency_scanner_service = DependencyScannerService()

__all__ = ["DependencyScannerService", "dependency_scanner_service"]
