"""
File: __init__.py
Purpose: Package initializer for the Terraform Generator service. Exposes the TerraformGeneratorService class and a singleton instance for generating Terraform HCL configurations across vSphere, Azure, AWS, and GCP providers.
When Used: Imported by the Terraform router and other modules that need to generate infrastructure-as-code configurations.
Why Created: Provides a clean entry point to the terraform package, following the same singleton pattern used by other service packages (pipeline, jenkins_pipeline, github_pipeline).
"""
from app.services.terraform.generator import TerraformGeneratorService

# Singleton instance
terraform_generator = TerraformGeneratorService()

__all__ = ["TerraformGeneratorService", "terraform_generator"]
