"""
File: azure.py
Purpose: Provides hardcoded default Terraform HCL templates for Azure infrastructure, covering Linux and Windows VMs, AKS Kubernetes clusters, ACI container groups, and VNet networking with subnets, NSG rules, and load balancers.
When Used: Called by the default_templates dispatcher when the user selects Azure as the provider and no ChromaDB or LLM-generated template is available.
Why Created: Ensures the Terraform generator always has a working baseline template for every Azure resource type, even when ChromaDB is empty and the LLM is unavailable or produces invalid output.
"""
from typing import Dict, Optional


def get_azure_template(resource_type: str, sub_type: Optional[str] = None) -> Dict[str, str]:
    """Dispatch to resource-specific Azure template."""
    templates = {
        "vm": _get_vm_template,
        "kubernetes": _get_kubernetes_template,
        "containers": _get_containers_template,
        "networking": _get_networking_template,
    }
    handler = templates.get(resource_type)
    if not handler:
        raise ValueError(f"Unknown resource type for Azure: {resource_type}")
    return handler(sub_type)


# ---------------------------------------------------------------------------
# Shared provider block (used by all templates)
# ---------------------------------------------------------------------------
_PROVIDER_TF = '''terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

provider "azurerm" {
  features {}

  subscription_id = var.subscription_id
  client_id       = var.client_id
  client_secret   = var.client_secret
  tenant_id       = var.tenant_id
}
'''

# ---------------------------------------------------------------------------
# Shared authentication variables (prepended to every variables.tf)
# ---------------------------------------------------------------------------
_AUTH_VARIABLES = '''# Azure Authentication
variable "subscription_id" {
  description = "Azure Subscription ID"
  type        = string
  sensitive   = true
}

variable "client_id" {
  description = "Azure Service Principal Client ID"
  type        = string
  sensitive   = true
}

variable "client_secret" {
  description = "Azure Service Principal Client Secret"
  type        = string
  sensitive   = true
}

variable "tenant_id" {
  description = "Azure AD Tenant ID"
  type        = string
  sensitive   = true
}

# Common
variable "prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default = {
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}
'''

# ---------------------------------------------------------------------------
# Shared tfvars header
# ---------------------------------------------------------------------------
_AUTH_TFVARS = '''# Azure Authentication
subscription_id = "00000000-0000-0000-0000-000000000000"
client_id       = "00000000-0000-0000-0000-000000000000"
client_secret   = "YOUR_CLIENT_SECRET"
tenant_id       = "00000000-0000-0000-0000-000000000000"

# Common
prefix   = "myapp"
location = "eastus"
'''


# ===========================================================================
# VM Template
# ===========================================================================
def _get_vm_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    os_type = sub_type or "linux"

    if os_type == "windows":
        return _get_windows_vm_files()
    return _get_linux_vm_files()


def _get_linux_vm_files() -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,
        "main.tf": '''# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = var.tags
}

# Virtual Network
resource "azurerm_virtual_network" "vnet" {
  name                = "${var.prefix}-vnet"
  address_space       = [var.vnet_address_space]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags
}

# Subnet
resource "azurerm_subnet" "subnet" {
  name                 = "${var.prefix}-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.subnet_address_prefix]
}

# Public IP
resource "azurerm_public_ip" "pip" {
  name                = "${var.prefix}-pip"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

# Network Security Group
resource "azurerm_network_security_group" "nsg" {
  name                = "${var.prefix}-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.allowed_ssh_cidr
    destination_address_prefix = "*"
  }
}

# Network Interface
resource "azurerm_network_interface" "nic" {
  name                = "${var.prefix}-nic"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.pip.id
  }
}

# Associate NSG with NIC
resource "azurerm_network_interface_security_group_association" "nic_nsg" {
  network_interface_id      = azurerm_network_interface.nic.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}

# Linux Virtual Machine
resource "azurerm_linux_virtual_machine" "vm" {
  name                = "${var.prefix}-vm"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = var.vm_size
  admin_username      = var.admin_username

  network_interface_ids = [
    azurerm_network_interface.nic.id,
  ]

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(var.ssh_public_key_path)
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = var.os_disk_type
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = var.image_publisher
    offer     = var.image_offer
    sku       = var.image_sku
    version   = var.image_version
  }

  tags = var.tags
}
''',
        "variables.tf": _AUTH_VARIABLES + '''
# VM Configuration
variable "vm_size" {
  description = "Azure VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "Admin username for the VM"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key file"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "os_disk_type" {
  description = "OS disk storage account type"
  type        = string
  default     = "Standard_LRS"
}

variable "os_disk_size_gb" {
  description = "OS disk size in GB"
  type        = number
  default     = 30
}

# Image
variable "image_publisher" {
  description = "VM image publisher"
  type        = string
  default     = "Canonical"
}

variable "image_offer" {
  description = "VM image offer"
  type        = string
  default     = "0001-com-ubuntu-server-jammy"
}

variable "image_sku" {
  description = "VM image SKU"
  type        = string
  default     = "22_04-lts-gen2"
}

variable "image_version" {
  description = "VM image version"
  type        = string
  default     = "latest"
}

# Network
variable "vnet_address_space" {
  description = "Virtual network address space"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_address_prefix" {
  description = "Subnet address prefix"
  type        = string
  default     = "10.0.1.0/24"
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed to SSH into the VM"
  type        = string
  default     = "*"
}
''',
        "outputs.tf": '''output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.rg.name
}

output "vm_id" {
  description = "ID of the virtual machine"
  value       = azurerm_linux_virtual_machine.vm.id
}

output "vm_name" {
  description = "Name of the virtual machine"
  value       = azurerm_linux_virtual_machine.vm.name
}

output "public_ip_address" {
  description = "Public IP address of the VM"
  value       = azurerm_public_ip.pip.ip_address
}

output "private_ip_address" {
  description = "Private IP address of the VM"
  value       = azurerm_network_interface.nic.private_ip_address
}

output "admin_username" {
  description = "Admin username for SSH access"
  value       = var.admin_username
}
''',
        "terraform.tfvars.example": _AUTH_TFVARS + '''
# VM Configuration
vm_size        = "Standard_B2s"
admin_username = "azureuser"
ssh_public_key_path = "~/.ssh/id_rsa.pub"
os_disk_size_gb     = 30

# Network
vnet_address_space    = "10.0.0.0/16"
subnet_address_prefix = "10.0.1.0/24"
allowed_ssh_cidr      = "203.0.113.0/24"

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }


def _get_windows_vm_files() -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,
        "main.tf": '''# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = var.tags
}

# Virtual Network
resource "azurerm_virtual_network" "vnet" {
  name                = "${var.prefix}-vnet"
  address_space       = [var.vnet_address_space]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags
}

# Subnet
resource "azurerm_subnet" "subnet" {
  name                 = "${var.prefix}-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.subnet_address_prefix]
}

# Public IP
resource "azurerm_public_ip" "pip" {
  name                = "${var.prefix}-pip"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

# Network Security Group
resource "azurerm_network_security_group" "nsg" {
  name                = "${var.prefix}-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  security_rule {
    name                       = "RDP"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3389"
    source_address_prefix      = var.allowed_rdp_cidr
    destination_address_prefix = "*"
  }
}

# Network Interface
resource "azurerm_network_interface" "nic" {
  name                = "${var.prefix}-nic"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.pip.id
  }
}

# Associate NSG with NIC
resource "azurerm_network_interface_security_group_association" "nic_nsg" {
  network_interface_id      = azurerm_network_interface.nic.id
  network_security_group_id = azurerm_network_security_group.nsg.id
}

# Windows Virtual Machine
resource "azurerm_windows_virtual_machine" "vm" {
  name                = "${var.prefix}-vm"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = var.vm_size
  admin_username      = var.admin_username
  admin_password      = var.admin_password

  network_interface_ids = [
    azurerm_network_interface.nic.id,
  ]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = var.os_disk_type
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = var.image_publisher
    offer     = var.image_offer
    sku       = var.image_sku
    version   = var.image_version
  }

  tags = var.tags
}
''',
        "variables.tf": _AUTH_VARIABLES + '''
# VM Configuration
variable "vm_size" {
  description = "Azure VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "Admin username for the VM"
  type        = string
  default     = "azureadmin"
}

variable "admin_password" {
  description = "Admin password for the Windows VM"
  type        = string
  sensitive   = true
}

variable "os_disk_type" {
  description = "OS disk storage account type"
  type        = string
  default     = "Standard_LRS"
}

variable "os_disk_size_gb" {
  description = "OS disk size in GB"
  type        = number
  default     = 128
}

# Image
variable "image_publisher" {
  description = "VM image publisher"
  type        = string
  default     = "MicrosoftWindowsServer"
}

variable "image_offer" {
  description = "VM image offer"
  type        = string
  default     = "WindowsServer"
}

variable "image_sku" {
  description = "VM image SKU"
  type        = string
  default     = "2022-datacenter-azure-edition"
}

variable "image_version" {
  description = "VM image version"
  type        = string
  default     = "latest"
}

# Network
variable "vnet_address_space" {
  description = "Virtual network address space"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_address_prefix" {
  description = "Subnet address prefix"
  type        = string
  default     = "10.0.1.0/24"
}

variable "allowed_rdp_cidr" {
  description = "CIDR block allowed to RDP into the VM"
  type        = string
  default     = "*"
}
''',
        "outputs.tf": '''output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.rg.name
}

output "vm_id" {
  description = "ID of the virtual machine"
  value       = azurerm_windows_virtual_machine.vm.id
}

output "vm_name" {
  description = "Name of the virtual machine"
  value       = azurerm_windows_virtual_machine.vm.name
}

output "public_ip_address" {
  description = "Public IP address of the VM"
  value       = azurerm_public_ip.pip.ip_address
}

output "private_ip_address" {
  description = "Private IP address of the VM"
  value       = azurerm_network_interface.nic.private_ip_address
}

output "admin_username" {
  description = "Admin username for RDP access"
  value       = var.admin_username
}
''',
        "terraform.tfvars.example": _AUTH_TFVARS + '''
# VM Configuration
vm_size        = "Standard_B2s"
admin_username = "azureadmin"
admin_password = "YOUR_ADMIN_PASSWORD"
os_disk_size_gb = 128

# Network
vnet_address_space    = "10.0.0.0/16"
subnet_address_prefix = "10.0.1.0/24"
allowed_rdp_cidr      = "203.0.113.0/24"

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }


# ===========================================================================
# Kubernetes (AKS) Template
# ===========================================================================
def _get_kubernetes_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,
        "main.tf": '''# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = var.tags
}

# Azure Kubernetes Service (AKS) Cluster
resource "azurerm_kubernetes_cluster" "aks" {
  name                = "${var.prefix}-aks"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "${var.prefix}-aks"
  kubernetes_version  = var.kubernetes_version

  default_node_pool {
    name                = "default"
    node_count          = var.node_count
    vm_size             = var.node_vm_size
    os_disk_size_gb     = var.node_os_disk_size_gb
    vnet_subnet_id      = var.vnet_subnet_id != "" ? var.vnet_subnet_id : null
    enable_auto_scaling = var.enable_auto_scaling
    min_count           = var.enable_auto_scaling ? var.min_node_count : null
    max_count           = var.enable_auto_scaling ? var.max_node_count : null
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin    = var.network_plugin
    network_policy    = var.network_policy
    load_balancer_sku = "standard"
    service_cidr      = var.service_cidr
    dns_service_ip    = var.dns_service_ip
  }

  tags = var.tags
}
''',
        "variables.tf": _AUTH_VARIABLES + '''
# AKS Configuration
variable "kubernetes_version" {
  description = "Kubernetes version for the AKS cluster"
  type        = string
  default     = "1.29"
}

variable "node_count" {
  description = "Initial number of nodes in the default pool"
  type        = number
  default     = 3
}

variable "node_vm_size" {
  description = "VM size for the default node pool"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "node_os_disk_size_gb" {
  description = "OS disk size for each node in GB"
  type        = number
  default     = 50
}

variable "vnet_subnet_id" {
  description = "Subnet ID for the default node pool (empty for auto-created)"
  type        = string
  default     = ""
}

# Auto Scaling
variable "enable_auto_scaling" {
  description = "Enable cluster auto-scaler for the default node pool"
  type        = bool
  default     = false
}

variable "min_node_count" {
  description = "Minimum number of nodes when auto-scaling is enabled"
  type        = number
  default     = 1
}

variable "max_node_count" {
  description = "Maximum number of nodes when auto-scaling is enabled"
  type        = number
  default     = 5
}

# Network
variable "network_plugin" {
  description = "Network plugin for AKS (azure or kubenet)"
  type        = string
  default     = "azure"
}

variable "network_policy" {
  description = "Network policy provider (azure, calico, or null)"
  type        = string
  default     = "azure"
}

variable "service_cidr" {
  description = "CIDR range for Kubernetes services"
  type        = string
  default     = "10.0.0.0/16"
}

variable "dns_service_ip" {
  description = "IP address for the Kubernetes DNS service"
  type        = string
  default     = "10.0.0.10"
}
''',
        "outputs.tf": '''output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.rg.name
}

output "cluster_id" {
  description = "ID of the AKS cluster"
  value       = azurerm_kubernetes_cluster.aks.id
}

output "cluster_name" {
  description = "Name of the AKS cluster"
  value       = azurerm_kubernetes_cluster.aks.name
}

output "cluster_fqdn" {
  description = "FQDN of the AKS cluster"
  value       = azurerm_kubernetes_cluster.aks.fqdn
}

output "kube_config_raw" {
  description = "Raw kubeconfig for the AKS cluster"
  value       = azurerm_kubernetes_cluster.aks.kube_config_raw
  sensitive   = true
}

output "kube_config_host" {
  description = "Kubernetes API server URL"
  value       = azurerm_kubernetes_cluster.aks.kube_config[0].host
  sensitive   = true
}

output "node_resource_group" {
  description = "Auto-created resource group for AKS nodes"
  value       = azurerm_kubernetes_cluster.aks.node_resource_group
}

output "identity_principal_id" {
  description = "Principal ID of the cluster managed identity"
  value       = azurerm_kubernetes_cluster.aks.identity[0].principal_id
}
''',
        "terraform.tfvars.example": _AUTH_TFVARS + '''
# AKS Configuration
kubernetes_version   = "1.29"
node_count           = 3
node_vm_size         = "Standard_D2s_v3"
node_os_disk_size_gb = 50

# Auto Scaling (optional)
enable_auto_scaling = false
# min_node_count    = 1
# max_node_count    = 5

# Network
network_plugin = "azure"
network_policy = "azure"
service_cidr   = "10.0.0.0/16"
dns_service_ip = "10.0.0.10"

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }


# ===========================================================================
# Containers (ACI) Template
# ===========================================================================
def _get_containers_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,
        "main.tf": '''# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = var.tags
}

# Azure Container Instance (ACI)
resource "azurerm_container_group" "aci" {
  name                = "${var.prefix}-aci"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = var.os_type
  restart_policy      = var.restart_policy
  ip_address_type     = var.ip_address_type
  dns_name_label      = "${var.prefix}-aci"

  container {
    name   = var.container_name
    image  = var.container_image
    cpu    = var.container_cpu
    memory = var.container_memory

    ports {
      port     = var.container_port
      protocol = "TCP"
    }

    environment_variables        = var.environment_variables
    secure_environment_variables = var.secure_environment_variables
  }

  tags = var.tags
}
''',
        "variables.tf": _AUTH_VARIABLES + '''
# Container Configuration
variable "container_name" {
  description = "Name of the container"
  type        = string
  default     = "nginx"
}

variable "container_image" {
  description = "Container image to deploy"
  type        = string
  default     = "nginx:latest"
}

variable "container_cpu" {
  description = "CPU cores allocated to the container"
  type        = number
  default     = 1
}

variable "container_memory" {
  description = "Memory (GB) allocated to the container"
  type        = number
  default     = 1.5
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
  default     = 80
}

variable "os_type" {
  description = "OS type for the container group (Linux or Windows)"
  type        = string
  default     = "Linux"
}

variable "restart_policy" {
  description = "Restart policy (Always, OnFailure, Never)"
  type        = string
  default     = "Always"
}

variable "ip_address_type" {
  description = "IP address type (Public or Private)"
  type        = string
  default     = "Public"
}

variable "environment_variables" {
  description = "Environment variables for the container"
  type        = map(string)
  default     = {}
}

variable "secure_environment_variables" {
  description = "Sensitive environment variables for the container"
  type        = map(string)
  default     = {}
  sensitive   = true
}
''',
        "outputs.tf": '''output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.rg.name
}

output "container_group_id" {
  description = "ID of the container group"
  value       = azurerm_container_group.aci.id
}

output "container_group_name" {
  description = "Name of the container group"
  value       = azurerm_container_group.aci.name
}

output "container_fqdn" {
  description = "FQDN of the container group"
  value       = azurerm_container_group.aci.fqdn
}

output "container_ip_address" {
  description = "Public IP address of the container group"
  value       = azurerm_container_group.aci.ip_address
}
''',
        "terraform.tfvars.example": _AUTH_TFVARS + '''
# Container Configuration
container_name  = "nginx"
container_image = "nginx:latest"
container_cpu   = 1
container_memory = 1.5
container_port  = 80

# Container Group
os_type         = "Linux"
restart_policy  = "Always"
ip_address_type = "Public"

# Environment Variables (optional)
# environment_variables = {
#   APP_ENV = "production"
# }

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }


# ===========================================================================
# Networking Template
# ===========================================================================
def _get_networking_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,
        "main.tf": '''# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = var.tags
}

# Virtual Network
resource "azurerm_virtual_network" "vnet" {
  name                = "${var.prefix}-vnet"
  address_space       = [var.vnet_address_space]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags
}

# Web Subnet
resource "azurerm_subnet" "web" {
  name                 = "${var.prefix}-web-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.web_subnet_prefix]
}

# App Subnet
resource "azurerm_subnet" "app" {
  name                 = "${var.prefix}-app-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.app_subnet_prefix]
}

# Database Subnet
resource "azurerm_subnet" "db" {
  name                 = "${var.prefix}-db-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = [var.db_subnet_prefix]
}

# Web Network Security Group
resource "azurerm_network_security_group" "web_nsg" {
  name                = "${var.prefix}-web-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  security_rule {
    name                       = "AllowHTTP"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowHTTPS"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# App Network Security Group
resource "azurerm_network_security_group" "app_nsg" {
  name                = "${var.prefix}-app-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  security_rule {
    name                       = "AllowWebSubnet"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8080"
    source_address_prefix      = var.web_subnet_prefix
    destination_address_prefix = "*"
  }
}

# Database Network Security Group
resource "azurerm_network_security_group" "db_nsg" {
  name                = "${var.prefix}-db-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  security_rule {
    name                       = "AllowAppSubnet"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "5432"
    source_address_prefix      = var.app_subnet_prefix
    destination_address_prefix = "*"
  }
}

# Associate NSGs with Subnets
resource "azurerm_subnet_network_security_group_association" "web" {
  subnet_id                 = azurerm_subnet.web.id
  network_security_group_id = azurerm_network_security_group.web_nsg.id
}

resource "azurerm_subnet_network_security_group_association" "app" {
  subnet_id                 = azurerm_subnet.app.id
  network_security_group_id = azurerm_network_security_group.app_nsg.id
}

resource "azurerm_subnet_network_security_group_association" "db" {
  subnet_id                 = azurerm_subnet.db.id
  network_security_group_id = azurerm_network_security_group.db_nsg.id
}

# Public IP for Load Balancer
resource "azurerm_public_ip" "lb_pip" {
  name                = "${var.prefix}-lb-pip"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = var.tags
}

# Load Balancer
resource "azurerm_lb" "lb" {
  name                = "${var.prefix}-lb"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Standard"
  tags                = var.tags

  frontend_ip_configuration {
    name                 = "PublicIPAddress"
    public_ip_address_id = azurerm_public_ip.lb_pip.id
  }
}

# Backend Address Pool
resource "azurerm_lb_backend_address_pool" "backend" {
  loadbalancer_id = azurerm_lb.lb.id
  name            = "${var.prefix}-backend-pool"
}

# Health Probe
resource "azurerm_lb_probe" "http" {
  loadbalancer_id = azurerm_lb.lb.id
  name            = "http-probe"
  protocol        = "Http"
  port            = 80
  request_path    = var.health_check_path
}

# Load Balancer Rule
resource "azurerm_lb_rule" "http" {
  loadbalancer_id                = azurerm_lb.lb.id
  name                           = "http-rule"
  protocol                       = "Tcp"
  frontend_port                  = 80
  backend_port                   = 80
  frontend_ip_configuration_name = "PublicIPAddress"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.backend.id]
  probe_id                       = azurerm_lb_probe.http.id
}
''',
        "variables.tf": _AUTH_VARIABLES + '''
# Network Configuration
variable "vnet_address_space" {
  description = "Virtual network address space"
  type        = string
  default     = "10.0.0.0/16"
}

variable "web_subnet_prefix" {
  description = "Address prefix for the web subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "app_subnet_prefix" {
  description = "Address prefix for the application subnet"
  type        = string
  default     = "10.0.2.0/24"
}

variable "db_subnet_prefix" {
  description = "Address prefix for the database subnet"
  type        = string
  default     = "10.0.3.0/24"
}

# Load Balancer
variable "health_check_path" {
  description = "Health check path for the load balancer probe"
  type        = string
  default     = "/"
}
''',
        "outputs.tf": '''output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.rg.name
}

output "vnet_id" {
  description = "ID of the virtual network"
  value       = azurerm_virtual_network.vnet.id
}

output "vnet_name" {
  description = "Name of the virtual network"
  value       = azurerm_virtual_network.vnet.name
}

output "web_subnet_id" {
  description = "ID of the web subnet"
  value       = azurerm_subnet.web.id
}

output "app_subnet_id" {
  description = "ID of the application subnet"
  value       = azurerm_subnet.app.id
}

output "db_subnet_id" {
  description = "ID of the database subnet"
  value       = azurerm_subnet.db.id
}

output "lb_id" {
  description = "ID of the load balancer"
  value       = azurerm_lb.lb.id
}

output "lb_public_ip" {
  description = "Public IP address of the load balancer"
  value       = azurerm_public_ip.lb_pip.ip_address
}

output "lb_backend_pool_id" {
  description = "ID of the load balancer backend pool"
  value       = azurerm_lb_backend_address_pool.backend.id
}

output "web_nsg_id" {
  description = "ID of the web network security group"
  value       = azurerm_network_security_group.web_nsg.id
}

output "app_nsg_id" {
  description = "ID of the application network security group"
  value       = azurerm_network_security_group.app_nsg.id
}

output "db_nsg_id" {
  description = "ID of the database network security group"
  value       = azurerm_network_security_group.db_nsg.id
}
''',
        "terraform.tfvars.example": _AUTH_TFVARS + '''
# Network Configuration
vnet_address_space = "10.0.0.0/16"
web_subnet_prefix  = "10.0.1.0/24"
app_subnet_prefix  = "10.0.2.0/24"
db_subnet_prefix   = "10.0.3.0/24"

# Load Balancer
health_check_path = "/"

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }
