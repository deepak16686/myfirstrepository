"""
File: __init__.py
Purpose: Package initializer for the Compliance Checker service. Exposes the ComplianceCheckerService class and a singleton instance for aggregating security and quality compliance data across projects.
When Used: Imported by the compliance checker router to serve the compliance dashboard, project listings, and per-project compliance reports to the frontend.
Why Created: Follows the singleton package pattern, providing a single import path for compliance checking that combines SonarQube quality gates with Trivy vulnerability scan data.
"""
from app.services.compliance_checker.service import ComplianceCheckerService

compliance_checker_service = ComplianceCheckerService()

__all__ = ["ComplianceCheckerService", "compliance_checker_service"]
