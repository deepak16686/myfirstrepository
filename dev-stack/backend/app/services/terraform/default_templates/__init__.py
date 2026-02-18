"""
File: __init__.py
Purpose: Dispatches default Terraform template requests to the correct provider-specific module (AWS, Azure, GCP, vSphere) based on the user's provider and resource type selection.
When Used: Called by the generator as a last-resort fallback when neither ChromaDB proven templates nor LLM generation produce valid results.
Why Created: Acts as a routing layer so the generator only needs to call one function (get_default_terraform_files) without knowing which provider module to import, keeping provider-specific template logic isolated.
"""
from typing import Dict, Optional

from app.services.terraform.default_templates.vsphere import get_vsphere_template
from app.services.terraform.default_templates.azure import get_azure_template
from app.services.terraform.default_templates.aws import get_aws_template
from app.services.terraform.default_templates.gcp import get_gcp_template


def get_default_terraform_files(
    provider: str,
    resource_type: str,
    sub_type: Optional[str] = None,
) -> Dict[str, str]:
    """
    Get default Terraform template files for a given provider/resource/subtype.

    Returns dict: {"provider.tf": ..., "main.tf": ..., "variables.tf": ...,
                    "outputs.tf": ..., "terraform.tfvars.example": ...}
    """
    dispatch = {
        "vsphere": get_vsphere_template,
        "azure": get_azure_template,
        "aws": get_aws_template,
        "gcp": get_gcp_template,
    }

    handler = dispatch.get(provider)
    if not handler:
        raise ValueError(f"Unknown provider: {provider}")

    return handler(resource_type, sub_type)
