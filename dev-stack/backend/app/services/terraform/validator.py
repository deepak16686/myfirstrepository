"""
File: validator.py
Purpose: Performs text-based validation of Terraform HCL files, checking for structural correctness (terraform/provider blocks, resource types), variable declaration consistency, and security issues (hardcoded credentials) without requiring the terraform CLI.
When Used: Called by the generator and LLM fixer as a fast pre-check before optionally running the heavier terraform init/validate CLI commands, catching obvious errors early.
Why Created: Provides a lightweight validation layer that works without the terraform binary installed, enabling quick feedback loops during iterative LLM fixing and catching common mistakes like missing provider blocks or undeclared variables.
"""
import re
from typing import Dict, List, Tuple


def validate_terraform_files(
    files: Dict[str, str],
    provider: str,
    resource_type: str,
    sub_type: str = None,
) -> Tuple[List[str], List[str]]:
    """
    Validate Terraform HCL files using text-based checks.

    Returns (errors, warnings).
    """
    errors = []
    warnings = []

    provider_tf = files.get("provider.tf", "")
    main_tf = files.get("main.tf", "")
    variables_tf = files.get("variables.tf", "")
    outputs_tf = files.get("outputs.tf", "")

    # --- Provider.tf checks ---
    if not provider_tf.strip():
        errors.append("provider.tf is empty")
    else:
        if "terraform {" not in provider_tf and "terraform{" not in provider_tf:
            errors.append("provider.tf missing terraform {} block with required_providers")

        if "required_providers" not in provider_tf:
            errors.append("provider.tf missing required_providers block")

        # Check provider block exists
        provider_names = {
            "vsphere": "vsphere",
            "azure": "azurerm",
            "aws": "aws",
            "gcp": "google",
        }
        expected_provider = provider_names.get(provider, provider)
        if f'provider "{expected_provider}"' not in provider_tf:
            errors.append(f'provider.tf missing provider "{expected_provider}" block')

    # --- Main.tf checks ---
    if not main_tf.strip():
        errors.append("main.tf is empty")
    else:
        if "resource " not in main_tf and "module " not in main_tf:
            errors.append("main.tf has no resource or module blocks")

        # Check for resource type relevance
        resource_keywords = {
            "vm": {
                "vsphere": ["vsphere_virtual_machine"],
                "azure": ["azurerm_linux_virtual_machine", "azurerm_windows_virtual_machine", "azurerm_virtual_machine"],
                "aws": ["aws_instance"],
                "gcp": ["google_compute_instance"],
            },
            "kubernetes": {
                "vsphere": ["vsphere_virtual_machine"],  # K8s on vSphere uses VMs
                "azure": ["azurerm_kubernetes_cluster"],
                "aws": ["aws_eks_cluster"],
                "gcp": ["google_container_cluster"],
            },
            "containers": {
                "vsphere": ["vsphere_virtual_machine"],
                "azure": ["azurerm_container_group", "azurerm_container_app"],
                "aws": ["aws_ecs_cluster", "aws_ecs_service"],
                "gcp": ["google_cloud_run_v2_service", "google_cloud_run_service"],
            },
            "networking": {
                "vsphere": ["vsphere_distributed_virtual_switch", "vsphere_distributed_port_group", "vsphere_host_virtual_switch"],
                "azure": ["azurerm_virtual_network", "azurerm_subnet"],
                "aws": ["aws_vpc", "aws_subnet"],
                "gcp": ["google_compute_network", "google_compute_subnetwork"],
            },
        }
        expected_resources = resource_keywords.get(resource_type, {}).get(provider, [])
        if expected_resources:
            found = any(r in main_tf for r in expected_resources)
            if not found:
                warnings.append(
                    f"main.tf doesn't contain expected resource types for {provider}/{resource_type}: "
                    f"{', '.join(expected_resources)}"
                )

    # --- Variables.tf checks ---
    if not variables_tf.strip():
        warnings.append("variables.tf is empty - consider adding configurable variables")
    else:
        # Check that referenced variables are declared
        var_refs = set(re.findall(r'var\.(\w+)', main_tf + provider_tf + outputs_tf))
        var_decls = set(re.findall(r'variable\s+"(\w+)"', variables_tf))
        undeclared = var_refs - var_decls
        if undeclared:
            errors.append(f"Variables referenced but not declared: {', '.join(sorted(undeclared))}")

    # --- Security checks ---
    all_content = main_tf + provider_tf + variables_tf + outputs_tf
    # Check for hardcoded credentials
    credential_patterns = [
        (r'password\s*=\s*"[^"]{3,}"', "Hardcoded password detected"),
        (r'secret\s*=\s*"[^"]{3,}"', "Hardcoded secret detected"),
        (r'api_key\s*=\s*"[^"]{3,}"', "Hardcoded API key detected"),
        (r'access_key\s*=\s*"AK[A-Z0-9]{18}"', "Hardcoded AWS access key detected"),
    ]
    for pattern, msg in credential_patterns:
        if re.search(pattern, all_content, re.IGNORECASE):
            errors.append(f"SECURITY: {msg} - use variables with sensitive=true instead")

    # --- Outputs.tf checks ---
    if not outputs_tf.strip():
        warnings.append("outputs.tf is empty - consider adding useful outputs (IPs, IDs, endpoints)")

    return errors, warnings
