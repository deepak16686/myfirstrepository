"""
Default Terraform Templates Dispatcher

Routes to the correct provider-specific template based on context.
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
