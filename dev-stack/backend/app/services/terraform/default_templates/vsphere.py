"""
File: vsphere.py
Purpose: Provides hardcoded default Terraform HCL templates for on-premises vSphere infrastructure, covering Linux/Windows VMs via template cloning, Kubernetes clusters deployed as kubeadm-bootstrapped VMs, Docker host VMs for container workloads, and distributed virtual switches with port groups.
When Used: Called by the default_templates dispatcher when the user selects vSphere as the provider and no ChromaDB or LLM-generated template is available.
Why Created: Ensures the Terraform generator always has a working baseline template for every vSphere resource type, even when ChromaDB is empty and the LLM is unavailable or produces invalid output.
"""
from typing import Dict, Optional


def get_vsphere_template(resource_type: str, sub_type: Optional[str] = None) -> Dict[str, str]:
    """Dispatch to resource-specific vSphere template."""
    templates = {
        "vm": _get_vm_template,
        "kubernetes": _get_kubernetes_template,
        "containers": _get_containers_template,
        "networking": _get_networking_template,
    }
    handler = templates.get(resource_type)
    if not handler:
        raise ValueError(f"Unknown resource type for vSphere: {resource_type}")
    return handler(sub_type)


def _get_vm_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    os_type = sub_type or "linux"
    guest_id = "ubuntu64Guest" if os_type == "linux" else "windows2019srv_64Guest"
    template_name = "ubuntu-2204-template" if os_type == "linux" else "windows-2019-template"

    return {
        "provider.tf": '''terraform {
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.6"
    }
  }
}

provider "vsphere" {
  vsphere_server       = var.vsphere_server
  user                 = var.vsphere_user
  password             = var.vsphere_password
  allow_unverified_ssl = var.allow_unverified_ssl
}
''',
        "main.tf": f'''# Data Sources
data "vsphere_datacenter" "dc" {{
  name = var.datacenter
}}

data "vsphere_datastore" "datastore" {{
  name          = var.datastore
  datacenter_id = data.vsphere_datacenter.dc.id
}}

data "vsphere_compute_cluster" "cluster" {{
  name          = var.cluster
  datacenter_id = data.vsphere_datacenter.dc.id
}}

data "vsphere_network" "network" {{
  name          = var.network
  datacenter_id = data.vsphere_datacenter.dc.id
}}

data "vsphere_virtual_machine" "template" {{
  name          = var.template_name
  datacenter_id = data.vsphere_datacenter.dc.id
}}

# Virtual Machine
resource "vsphere_virtual_machine" "vm" {{
  name             = "${{var.prefix}}-{os_type}-vm"
  resource_pool_id = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  folder           = var.folder

  num_cpus = var.cpu_count
  memory   = var.memory_mb
  guest_id = data.vsphere_virtual_machine.template.guest_id

  network_interface {{
    network_id   = data.vsphere_network.network.id
    adapter_type = data.vsphere_virtual_machine.template.network_interface_types[0]
  }}

  disk {{
    label            = "disk0"
    size             = var.disk_size_gb
    eagerly_scrub    = false
    thin_provisioned = true
  }}

  clone {{
    template_uuid = data.vsphere_virtual_machine.template.id

    customize {{
      {"linux_options {" if os_type == "linux" else "windows_options {"}
        {"host_name = var.hostname" if os_type == "linux" else "computer_name = var.hostname"}
        {"domain    = var.domain" if os_type == "linux" else "admin_password = var.admin_password"}
      }}

      network_interface {{
        ipv4_address = var.ip_address
        ipv4_netmask = var.netmask
      }}
      ipv4_gateway    = var.gateway
      dns_server_list = var.dns_servers
    }}
  }}

  tags = [for k, v in var.tags : "${{k}}:${{v}}"]
}}
''',
        "variables.tf": f'''# vSphere Connection
variable "vsphere_server" {{
  description = "vCenter server address"
  type        = string
  sensitive   = true
}}

variable "vsphere_user" {{
  description = "vCenter username"
  type        = string
  sensitive   = true
}}

variable "vsphere_password" {{
  description = "vCenter password"
  type        = string
  sensitive   = true
}}

variable "allow_unverified_ssl" {{
  description = "Allow unverified SSL certificates"
  type        = bool
  default     = true
}}

# Infrastructure
variable "datacenter" {{
  description = "vSphere datacenter name"
  type        = string
  default     = "Datacenter"
}}

variable "cluster" {{
  description = "vSphere compute cluster name"
  type        = string
  default     = "Cluster"
}}

variable "datastore" {{
  description = "vSphere datastore name"
  type        = string
  default     = "datastore1"
}}

variable "network" {{
  description = "vSphere network name"
  type        = string
  default     = "VM Network"
}}

variable "folder" {{
  description = "vSphere VM folder"
  type        = string
  default     = ""
}}

# VM Configuration
variable "prefix" {{
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}}

variable "template_name" {{
  description = "VM template to clone"
  type        = string
  default     = "{template_name}"
}}

variable "hostname" {{
  description = "VM hostname"
  type        = string
  default     = "{os_type}-vm-01"
}}

variable "domain" {{
  description = "Domain name for the VM"
  type        = string
  default     = "local.domain"
}}

variable "cpu_count" {{
  description = "Number of CPUs"
  type        = number
  default     = 2
}}

variable "memory_mb" {{
  description = "Memory in MB"
  type        = number
  default     = 4096
}}

variable "disk_size_gb" {{
  description = "Disk size in GB"
  type        = number
  default     = 50
}}

# Network
variable "ip_address" {{
  description = "Static IP address"
  type        = string
  default     = "192.168.1.100"
}}

variable "netmask" {{
  description = "Subnet mask bits"
  type        = number
  default     = 24
}}

variable "gateway" {{
  description = "Default gateway"
  type        = string
  default     = "192.168.1.1"
}}

variable "dns_servers" {{
  description = "DNS server list"
  type        = list(string)
  default     = ["8.8.8.8", "8.8.4.4"]
}}

{"" if os_type == "linux" else """variable "admin_password" {
  description = "Windows administrator password"
  type        = string
  sensitive   = true
}
"""}
variable "tags" {{
  description = "Resource tags"
  type        = map(string)
  default = {{
    Environment = "dev"
    ManagedBy   = "terraform"
  }}
}}
''',
        "outputs.tf": '''output "vm_id" {
  description = "Virtual machine ID"
  value       = vsphere_virtual_machine.vm.id
}

output "vm_name" {
  description = "Virtual machine name"
  value       = vsphere_virtual_machine.vm.name
}

output "vm_ip" {
  description = "Virtual machine IP address"
  value       = vsphere_virtual_machine.vm.default_ip_address
}

output "vm_uuid" {
  description = "Virtual machine UUID"
  value       = vsphere_virtual_machine.vm.uuid
}
''',
        "terraform.tfvars.example": f'''# vSphere Connection
vsphere_server   = "vcenter.example.com"
vsphere_user     = "administrator@vsphere.local"
vsphere_password  = "YOUR_VCENTER_PASSWORD"

# Infrastructure
datacenter    = "Datacenter"
cluster       = "Cluster"
datastore     = "datastore1"
network       = "VM Network"
template_name = "{template_name}"

# VM Configuration
prefix      = "myapp"
hostname    = "{os_type}-vm-01"
cpu_count   = 2
memory_mb   = 4096
disk_size_gb = 50

# Network
ip_address  = "192.168.1.100"
netmask     = 24
gateway     = "192.168.1.1"
dns_servers = ["8.8.8.8", "8.8.4.4"]
{"admin_password = " + '"YOUR_ADMIN_PASSWORD"' if os_type == "windows" else ""}
''',
    }


def _get_kubernetes_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": '''terraform {
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.6"
    }
  }
}

provider "vsphere" {
  vsphere_server       = var.vsphere_server
  user                 = var.vsphere_user
  password             = var.vsphere_password
  allow_unverified_ssl = var.allow_unverified_ssl
}
''',
        "main.tf": '''# Data Sources
data "vsphere_datacenter" "dc" {
  name = var.datacenter
}

data "vsphere_datastore" "datastore" {
  name          = var.datastore
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_compute_cluster" "cluster" {
  name          = var.cluster
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_network" "network" {
  name          = var.network
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_virtual_machine" "template" {
  name          = var.template_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

# Control Plane Nodes
resource "vsphere_virtual_machine" "control_plane" {
  count            = var.control_plane_count
  name             = "${var.prefix}-k8s-cp-${count.index + 1}"
  resource_pool_id = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id

  num_cpus = var.cp_cpu_count
  memory   = var.cp_memory_mb
  guest_id = data.vsphere_virtual_machine.template.guest_id

  network_interface {
    network_id   = data.vsphere_network.network.id
    adapter_type = data.vsphere_virtual_machine.template.network_interface_types[0]
  }

  disk {
    label            = "disk0"
    size             = var.cp_disk_size_gb
    eagerly_scrub    = false
    thin_provisioned = true
  }

  clone {
    template_uuid = data.vsphere_virtual_machine.template.id
    customize {
      linux_options {
        host_name = "${var.prefix}-k8s-cp-${count.index + 1}"
        domain    = var.domain
      }
      network_interface {
        ipv4_address = cidrhost(var.network_cidr, var.cp_ip_start + count.index)
        ipv4_netmask = var.netmask
      }
      ipv4_gateway    = var.gateway
      dns_server_list = var.dns_servers
    }
  }
}

# Worker Nodes
resource "vsphere_virtual_machine" "worker" {
  count            = var.worker_count
  name             = "${var.prefix}-k8s-worker-${count.index + 1}"
  resource_pool_id = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id

  num_cpus = var.worker_cpu_count
  memory   = var.worker_memory_mb
  guest_id = data.vsphere_virtual_machine.template.guest_id

  network_interface {
    network_id   = data.vsphere_network.network.id
    adapter_type = data.vsphere_virtual_machine.template.network_interface_types[0]
  }

  disk {
    label            = "disk0"
    size             = var.worker_disk_size_gb
    eagerly_scrub    = false
    thin_provisioned = true
  }

  clone {
    template_uuid = data.vsphere_virtual_machine.template.id
    customize {
      linux_options {
        host_name = "${var.prefix}-k8s-worker-${count.index + 1}"
        domain    = var.domain
      }
      network_interface {
        ipv4_address = cidrhost(var.network_cidr, var.worker_ip_start + count.index)
        ipv4_netmask = var.netmask
      }
      ipv4_gateway    = var.gateway
      dns_server_list = var.dns_servers
    }
  }
}
''',
        "variables.tf": '''variable "vsphere_server" {
  description = "vCenter server address"
  type        = string
  sensitive   = true
}
variable "vsphere_user" {
  description = "vCenter username"
  type        = string
  sensitive   = true
}
variable "vsphere_password" {
  description = "vCenter password"
  type        = string
  sensitive   = true
}
variable "allow_unverified_ssl" {
  type    = bool
  default = true
}
variable "prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}
variable "datacenter" {
  type    = string
  default = "Datacenter"
}
variable "cluster" {
  type    = string
  default = "Cluster"
}
variable "datastore" {
  type    = string
  default = "datastore1"
}
variable "network" {
  type    = string
  default = "VM Network"
}
variable "template_name" {
  type    = string
  default = "ubuntu-2204-template"
}
variable "domain" {
  type    = string
  default = "local.domain"
}
variable "network_cidr" {
  type    = string
  default = "192.168.1.0/24"
}
variable "netmask" {
  type    = number
  default = 24
}
variable "gateway" {
  type    = string
  default = "192.168.1.1"
}
variable "dns_servers" {
  type    = list(string)
  default = ["8.8.8.8", "8.8.4.4"]
}
variable "control_plane_count" {
  description = "Number of control plane nodes"
  type        = number
  default     = 3
}
variable "cp_cpu_count" {
  type    = number
  default = 4
}
variable "cp_memory_mb" {
  type    = number
  default = 8192
}
variable "cp_disk_size_gb" {
  type    = number
  default = 100
}
variable "cp_ip_start" {
  description = "Starting IP host number for control plane"
  type        = number
  default     = 10
}
variable "worker_count" {
  description = "Number of worker nodes"
  type        = number
  default     = 3
}
variable "worker_cpu_count" {
  type    = number
  default = 4
}
variable "worker_memory_mb" {
  type    = number
  default = 16384
}
variable "worker_disk_size_gb" {
  type    = number
  default = 200
}
variable "worker_ip_start" {
  description = "Starting IP host number for workers"
  type        = number
  default     = 20
}
''',
        "outputs.tf": '''output "control_plane_ips" {
  description = "Control plane node IP addresses"
  value       = vsphere_virtual_machine.control_plane[*].default_ip_address
}
output "worker_ips" {
  description = "Worker node IP addresses"
  value       = vsphere_virtual_machine.worker[*].default_ip_address
}
output "control_plane_names" {
  value = vsphere_virtual_machine.control_plane[*].name
}
output "worker_names" {
  value = vsphere_virtual_machine.worker[*].name
}
''',
        "terraform.tfvars.example": '''vsphere_server   = "vcenter.example.com"
vsphere_user     = "administrator@vsphere.local"
vsphere_password = "YOUR_PASSWORD"

prefix              = "myapp"
datacenter          = "Datacenter"
cluster             = "Cluster"
datastore           = "datastore1"
network             = "VM Network"
template_name       = "ubuntu-2204-template"
control_plane_count = 3
worker_count        = 3
''',
    }


def _get_containers_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": '''terraform {
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.6"
    }
  }
}

provider "vsphere" {
  vsphere_server       = var.vsphere_server
  user                 = var.vsphere_user
  password             = var.vsphere_password
  allow_unverified_ssl = var.allow_unverified_ssl
}
''',
        "main.tf": '''data "vsphere_datacenter" "dc" {
  name = var.datacenter
}
data "vsphere_datastore" "datastore" {
  name          = var.datastore
  datacenter_id = data.vsphere_datacenter.dc.id
}
data "vsphere_compute_cluster" "cluster" {
  name          = var.cluster
  datacenter_id = data.vsphere_datacenter.dc.id
}
data "vsphere_network" "network" {
  name          = var.network
  datacenter_id = data.vsphere_datacenter.dc.id
}
data "vsphere_virtual_machine" "template" {
  name          = var.template_name
  datacenter_id = data.vsphere_datacenter.dc.id
}

# Docker Host VMs
resource "vsphere_virtual_machine" "docker_host" {
  count            = var.host_count
  name             = "${var.prefix}-docker-${count.index + 1}"
  resource_pool_id = data.vsphere_compute_cluster.cluster.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id

  num_cpus = var.cpu_count
  memory   = var.memory_mb
  guest_id = data.vsphere_virtual_machine.template.guest_id

  network_interface {
    network_id   = data.vsphere_network.network.id
    adapter_type = data.vsphere_virtual_machine.template.network_interface_types[0]
  }

  disk {
    label            = "disk0"
    size             = var.disk_size_gb
    eagerly_scrub    = false
    thin_provisioned = true
  }

  clone {
    template_uuid = data.vsphere_virtual_machine.template.id
    customize {
      linux_options {
        host_name = "${var.prefix}-docker-${count.index + 1}"
        domain    = var.domain
      }
      network_interface {
        ipv4_address = cidrhost(var.network_cidr, var.ip_start + count.index)
        ipv4_netmask = var.netmask
      }
      ipv4_gateway    = var.gateway
      dns_server_list = var.dns_servers
    }
  }
}
''',
        "variables.tf": '''variable "vsphere_server" { type = string; sensitive = true }
variable "vsphere_user" { type = string; sensitive = true }
variable "vsphere_password" { type = string; sensitive = true }
variable "allow_unverified_ssl" { type = bool; default = true }
variable "prefix" { type = string; default = "myapp" }
variable "datacenter" { type = string; default = "Datacenter" }
variable "cluster" { type = string; default = "Cluster" }
variable "datastore" { type = string; default = "datastore1" }
variable "network" { type = string; default = "VM Network" }
variable "template_name" { type = string; default = "ubuntu-2204-docker-template" }
variable "domain" { type = string; default = "local.domain" }
variable "host_count" { description = "Number of Docker hosts"; type = number; default = 2 }
variable "cpu_count" { type = number; default = 4 }
variable "memory_mb" { type = number; default = 8192 }
variable "disk_size_gb" { type = number; default = 100 }
variable "network_cidr" { type = string; default = "192.168.1.0/24" }
variable "netmask" { type = number; default = 24 }
variable "gateway" { type = string; default = "192.168.1.1" }
variable "dns_servers" { type = list(string); default = ["8.8.8.8"] }
variable "ip_start" { type = number; default = 30 }
''',
        "outputs.tf": '''output "docker_host_ips" {
  value = vsphere_virtual_machine.docker_host[*].default_ip_address
}
output "docker_host_names" {
  value = vsphere_virtual_machine.docker_host[*].name
}
''',
        "terraform.tfvars.example": '''vsphere_server   = "vcenter.example.com"
vsphere_user     = "administrator@vsphere.local"
vsphere_password = "YOUR_PASSWORD"
prefix           = "myapp"
host_count       = 2
cpu_count        = 4
memory_mb        = 8192
''',
    }


def _get_networking_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": '''terraform {
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.6"
    }
  }
}

provider "vsphere" {
  vsphere_server       = var.vsphere_server
  user                 = var.vsphere_user
  password             = var.vsphere_password
  allow_unverified_ssl = var.allow_unverified_ssl
}
''',
        "main.tf": '''data "vsphere_datacenter" "dc" {
  name = var.datacenter
}

data "vsphere_host" "hosts" {
  count         = length(var.esxi_hosts)
  name          = var.esxi_hosts[count.index]
  datacenter_id = data.vsphere_datacenter.dc.id
}

# Distributed Virtual Switch
resource "vsphere_distributed_virtual_switch" "dvs" {
  name          = "${var.prefix}-dvs"
  datacenter_id = data.vsphere_datacenter.dc.id

  dynamic "host" {
    for_each = data.vsphere_host.hosts
    content {
      host_system_id = host.value.id
      devices        = var.uplink_devices
    }
  }

  uplinks         = var.uplink_names
  active_uplinks  = [var.uplink_names[0]]
  standby_uplinks = length(var.uplink_names) > 1 ? [var.uplink_names[1]] : []
}

# Port Groups
resource "vsphere_distributed_port_group" "pg" {
  for_each                        = var.port_groups
  name                            = "${var.prefix}-${each.key}"
  distributed_virtual_switch_uuid = vsphere_distributed_virtual_switch.dvs.id
  vlan_id                         = each.value.vlan_id
  number_of_ports                 = each.value.ports

  allow_promiscuous      = each.value.allow_promiscuous
  allow_forged_transmits = each.value.allow_forged_transmits
  allow_mac_changes      = each.value.allow_mac_changes
}
''',
        "variables.tf": '''variable "vsphere_server" { type = string; sensitive = true }
variable "vsphere_user" { type = string; sensitive = true }
variable "vsphere_password" { type = string; sensitive = true }
variable "allow_unverified_ssl" { type = bool; default = true }
variable "prefix" { type = string; default = "myapp" }
variable "datacenter" { type = string; default = "Datacenter" }
variable "esxi_hosts" {
  description = "List of ESXi host names"
  type        = list(string)
  default     = ["esxi-01.local", "esxi-02.local"]
}
variable "uplink_devices" {
  description = "Physical NIC devices for uplinks"
  type        = list(string)
  default     = ["vmnic0", "vmnic1"]
}
variable "uplink_names" {
  type    = list(string)
  default = ["uplink1", "uplink2"]
}
variable "port_groups" {
  description = "Port group configurations"
  type = map(object({
    vlan_id              = number
    ports                = number
    allow_promiscuous    = bool
    allow_forged_transmits = bool
    allow_mac_changes    = bool
  }))
  default = {
    "management" = { vlan_id = 10, ports = 24, allow_promiscuous = false, allow_forged_transmits = false, allow_mac_changes = false }
    "production" = { vlan_id = 20, ports = 128, allow_promiscuous = false, allow_forged_transmits = false, allow_mac_changes = false }
    "dmz"        = { vlan_id = 30, ports = 24, allow_promiscuous = false, allow_forged_transmits = false, allow_mac_changes = false }
  }
}
''',
        "outputs.tf": '''output "dvs_id" {
  value = vsphere_distributed_virtual_switch.dvs.id
}
output "port_group_ids" {
  value = { for k, v in vsphere_distributed_port_group.pg : k => v.id }
}
output "port_group_names" {
  value = { for k, v in vsphere_distributed_port_group.pg : k => v.name }
}
''',
        "terraform.tfvars.example": '''vsphere_server = "vcenter.example.com"
vsphere_user   = "administrator@vsphere.local"
vsphere_password = "YOUR_PASSWORD"
prefix         = "myapp"
esxi_hosts     = ["esxi-01.local", "esxi-02.local"]
''',
    }
