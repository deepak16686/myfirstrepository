"""
File: analyzer.py
Purpose: Builds context descriptions, provider configurations, and resource-specific generation hints for Terraform HCL generation. Structures the user's provider and resource type selection into structured context that the LLM and validator can consume.
When Used: Called by the TerraformGeneratorService during generation to build prompts, and by the Terraform router to serve the provider/resource tree to the frontend.
Why Created: Separates context-building logic from the main generator facade, providing provider-specific requirements and hints (e.g., which Azure resources to use for VMs vs. Kubernetes) without cluttering the orchestration layer.
"""
from typing import Dict, Any, Optional

from app.services.terraform.constants import (
    PROVIDERS,
    RESOURCE_TYPES,
    PROVIDER_SOURCES,
    PROVIDER_VERSIONS,
    PROVIDER_CREDENTIALS,
    RESOURCE_DISPLAY_NAMES,
)


def build_context_description(provider: str, resource_type: str, sub_type: str = None) -> str:
    """Build human-readable description of what we're generating."""
    provider_name = PROVIDERS.get(provider, {}).get("name", provider)
    resource_name = RESOURCE_DISPLAY_NAMES.get(resource_type, resource_type)

    desc = f"{resource_name} on {provider_name}"
    if sub_type:
        desc += f" ({sub_type.capitalize()})"
    return desc


def get_provider_config(provider: str) -> Dict[str, Any]:
    """Return provider source, version, and required auth variables."""
    return {
        "source": PROVIDER_SOURCES.get(provider, f"hashicorp/{provider}"),
        "version": PROVIDER_VERSIONS.get(provider, "~> 1.0"),
        "credentials": PROVIDER_CREDENTIALS.get(provider, []),
        "name": PROVIDERS.get(provider, {}).get("name", provider),
    }


def get_resource_requirements(provider: str, resource_type: str, sub_type: str = None) -> Dict[str, Any]:
    """Return resource-specific generation hints for the LLM."""
    requirements = {
        "provider": provider,
        "resource_type": resource_type,
        "sub_type": sub_type,
        "description": build_context_description(provider, resource_type, sub_type),
    }

    # Provider + resource specific hints
    if provider == "vsphere":
        requirements["notes"] = [
            "Use vsphere_virtual_machine resource for VMs",
            "Requires datacenter, datastore, resource_pool, and network data sources",
            "Use template cloning for VM creation (clone block)",
            "Customize with vapp properties or customization spec",
        ]
        if resource_type == "kubernetes":
            requirements["notes"].append("Deploy K8s nodes as VMs, use cloud-init for kubeadm setup")
        elif resource_type == "containers":
            requirements["notes"].append("Deploy Docker host VMs with Docker pre-installed via cloud-init")
        elif resource_type == "networking":
            requirements["notes"] = [
                "Use vsphere_distributed_virtual_switch and vsphere_distributed_port_group",
                "Configure VLANs, uplinks, and traffic shaping",
            ]

    elif provider == "azure":
        if resource_type == "vm":
            os_type = sub_type or "linux"
            if os_type == "linux":
                requirements["notes"] = [
                    "Use azurerm_linux_virtual_machine resource",
                    "Include resource group, vnet, subnet, NIC, and public IP",
                    "Use admin_ssh_key for authentication",
                ]
            else:
                requirements["notes"] = [
                    "Use azurerm_windows_virtual_machine resource",
                    "Include resource group, vnet, subnet, NIC, and public IP",
                    "Use admin_password with winrm for access",
                ]
        elif resource_type == "kubernetes":
            requirements["notes"] = [
                "Use azurerm_kubernetes_cluster for AKS",
                "Include default_node_pool configuration",
                "Configure identity (SystemAssigned), network_profile",
            ]
        elif resource_type == "containers":
            requirements["notes"] = [
                "Use azurerm_container_group for ACI (simple containers)",
                "Include container definition with image, cpu, memory, ports",
            ]
        elif resource_type == "networking":
            requirements["notes"] = [
                "Use azurerm_virtual_network, azurerm_subnet",
                "Include azurerm_network_security_group with rules",
                "Optionally add azurerm_public_ip and azurerm_lb",
            ]

    elif provider == "aws":
        if resource_type == "vm":
            requirements["notes"] = [
                "Use aws_instance resource",
                "Include VPC, subnet, security group, and key pair",
                "Use data source for AMI lookup (Amazon Linux 2023 or Ubuntu)",
            ]
            if sub_type == "windows":
                requirements["notes"].append("Use Windows Server AMI, configure get_password_data")
        elif resource_type == "kubernetes":
            requirements["notes"] = [
                "Use aws_eks_cluster and aws_eks_node_group",
                "Include IAM roles for cluster and node group",
                "Configure VPC with public and private subnets",
            ]
        elif resource_type == "containers":
            requirements["notes"] = [
                "Use aws_ecs_cluster, aws_ecs_service, aws_ecs_task_definition",
                "Use Fargate launch type for serverless containers",
                "Include ALB for service discovery/load balancing",
            ]
        elif resource_type == "networking":
            requirements["notes"] = [
                "Use aws_vpc, aws_subnet (public + private)",
                "Include aws_internet_gateway, aws_nat_gateway, aws_route_table",
                "Add aws_security_group with ingress/egress rules",
            ]

    elif provider == "gcp":
        if resource_type == "vm":
            requirements["notes"] = [
                "Use google_compute_instance resource",
                "Include google_compute_network and google_compute_subnetwork",
                "Configure boot_disk with image, network_interface with access_config",
            ]
            if sub_type == "windows":
                requirements["notes"].append("Use Windows Server image, add metadata for sysprep")
        elif resource_type == "kubernetes":
            requirements["notes"] = [
                "Use google_container_cluster for GKE",
                "Include google_container_node_pool",
                "Configure initial_node_count, node_config with machine_type",
            ]
        elif resource_type == "containers":
            requirements["notes"] = [
                "Use google_cloud_run_v2_service for Cloud Run",
                "Configure template with containers, ports, resources",
                "Set ingress to INGRESS_TRAFFIC_ALL for public access",
            ]
        elif resource_type == "networking":
            requirements["notes"] = [
                "Use google_compute_network (auto or custom mode)",
                "Include google_compute_subnetwork, google_compute_firewall",
                "Add google_compute_router and google_compute_router_nat for NAT",
            ]

    return requirements


def get_providers_tree() -> Dict[str, Any]:
    """Return the full provider/resource/subtype tree for frontend rendering."""
    providers = []
    for pid, pinfo in PROVIDERS.items():
        provider = {
            "id": pid,
            "name": pinfo["name"],
            "icon": pinfo["icon"],
            "color": pinfo["color"],
            "resources": [],
        }
        for rid, rinfo in RESOURCE_TYPES.items():
            resource = {
                "id": rid,
                "name": rinfo["name"],
                "icon": rinfo["icon"],
                "sub_types": None,
            }
            if rinfo.get("sub_types"):
                resource["sub_types"] = [
                    {"id": sid, "name": sinfo["name"], "icon": sinfo["icon"]}
                    for sid, sinfo in rinfo["sub_types"].items()
                ]
            provider["resources"].append(resource)
        providers.append(provider)

    return {"providers": providers}
