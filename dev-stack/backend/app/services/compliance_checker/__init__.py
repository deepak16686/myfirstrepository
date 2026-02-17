"""Compliance Checker Service Package."""
from app.services.compliance_checker.service import ComplianceCheckerService

compliance_checker_service = ComplianceCheckerService()

__all__ = ["ComplianceCheckerService", "compliance_checker_service"]
