"""Terraform Generator Service Package.

Generates Terraform HCL configurations for multiple cloud providers.
Supports vSphere (On-Prem), Azure, AWS, and GCP with resource types:
Virtual Machines, Kubernetes Clusters, Container Services, and Networking.
"""
from app.services.terraform.generator import TerraformGeneratorService

# Singleton instance
terraform_generator = TerraformGeneratorService()

__all__ = ["TerraformGeneratorService", "terraform_generator"]
