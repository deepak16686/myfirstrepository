"""
File: constants.py
Purpose: Defines all module-level constants for the Terraform generator, including supported cloud providers (vSphere, Azure, AWS, GCP), resource types (VM, Kubernetes, Containers, Networking), provider source/version constraints, credential variable names, and ChromaDB collection names.
When Used: Imported throughout the terraform package by the analyzer, generator, validator, learning, and templates modules to ensure consistent provider and resource definitions.
Why Created: Centralizes magic strings and configuration data that would otherwise be duplicated across multiple modules, making it easy to add new providers or resource types in one place.
"""

FEEDBACK_COLLECTION = "terraform_feedback"
TEMPLATES_COLLECTION = "terraform_templates"
SUCCESSFUL_COLLECTION = "terraform_successful_configs"
DEFAULT_MODEL = "pipeline-generator-v5"

PROVIDERS = {
    "vsphere": {"name": "On-Prem (vSphere)", "icon": "server", "color": "#6366f1"},
    "azure": {"name": "Azure", "icon": "cloud", "color": "#0078d4"},
    "aws": {"name": "AWS", "icon": "cloud", "color": "#ff9900"},
    "gcp": {"name": "GCP", "icon": "cloud", "color": "#4285f4"},
}

RESOURCE_TYPES = {
    "vm": {
        "name": "Virtual Machines",
        "icon": "monitor",
        "sub_types": {
            "linux": {"name": "Linux", "icon": "linux"},
            "windows": {"name": "Windows", "icon": "windows"},
        },
    },
    "kubernetes": {"name": "Kubernetes Clusters", "icon": "k8s", "sub_types": None},
    "containers": {"name": "Container Services", "icon": "container", "sub_types": None},
    "networking": {"name": "Networking", "icon": "network", "sub_types": None},
}

# Terraform provider source and version constraints
PROVIDER_SOURCES = {
    "vsphere": "hashicorp/vsphere",
    "azure": "hashicorp/azurerm",
    "aws": "hashicorp/aws",
    "gcp": "hashicorp/google",
}

PROVIDER_VERSIONS = {
    "vsphere": "~> 2.6",
    "azure": "~> 3.100",
    "aws": "~> 5.40",
    "gcp": "~> 5.20",
}

# Provider-specific required variables (credentials)
PROVIDER_CREDENTIALS = {
    "vsphere": ["vsphere_server", "vsphere_user", "vsphere_password"],
    "azure": ["subscription_id", "client_id", "client_secret", "tenant_id"],
    "aws": ["aws_access_key", "aws_secret_key", "aws_region"],
    "gcp": ["gcp_project", "gcp_region"],
}

# Friendly display names for resource types
RESOURCE_DISPLAY_NAMES = {
    "vm": "Virtual Machine",
    "kubernetes": "Kubernetes Cluster",
    "containers": "Container Service",
    "networking": "Network Infrastructure",
}
