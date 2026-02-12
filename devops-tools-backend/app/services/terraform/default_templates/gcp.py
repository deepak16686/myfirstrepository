"""
GCP (Google Cloud Platform) Default Terraform Templates

Templates for Google Cloud infrastructure:
- Virtual Machines (Compute Engine - Linux/Windows)
- Kubernetes Clusters (GKE)
- Container Services (Cloud Run)
- Networking (VPC, Subnets, Firewall, Cloud NAT)
"""
from typing import Dict, Optional


def get_gcp_template(resource_type: str, sub_type: Optional[str] = None) -> Dict[str, str]:
    """Dispatch to resource-specific GCP template."""
    templates = {
        "vm": _get_vm_template,
        "kubernetes": _get_kubernetes_template,
        "containers": _get_containers_template,
        "networking": _get_networking_template,
    }
    handler = templates.get(resource_type)
    if not handler:
        raise ValueError(f"Unknown resource type for GCP: {resource_type}")
    return handler(sub_type)


def _get_vm_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    os_type = sub_type or "linux"

    if os_type == "windows":
        boot_disk_image = "windows-cloud/windows-server-2022-dc-v20240415"
        boot_disk_size = 100
        metadata_block = '''
  metadata = {
    windows-startup-script-ps1 = "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Force"
    enable-windows-ssh         = "TRUE"
    sysprep-specialize-script-cmd = "googet -noconfirm=true install google-compute-engine-ssh"
  }'''
        extra_firewall = '''
# Allow RDP
resource "google_compute_firewall" "allow_rdp" {
  name    = "${var.prefix}-allow-rdp"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {
    protocol = "tcp"
    ports    = ["3389"]
  }

  source_ranges = var.allowed_source_ranges
  target_tags   = ["${var.prefix}-vm"]
}
'''
        extra_output = '''
output "rdp_command" {
  description = "RDP connection info"
  value       = "Connect via RDP to ${google_compute_address.static_ip.address}:3389"
}
'''
    else:
        boot_disk_image = "debian-cloud/debian-12"
        boot_disk_size = 50
        metadata_block = '''
  metadata = {
    ssh-keys       = "${var.ssh_user}:${var.ssh_public_key}"
    enable-oslogin = "FALSE"
  }'''
        extra_firewall = ""
        extra_output = '''
output "ssh_command" {
  description = "SSH connection command"
  value       = "ssh ${var.ssh_user}@${google_compute_address.static_ip.address}"
}
'''

    return {
        "provider.tf": '''terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
  zone    = var.gcp_zone
}
''',
        "main.tf": f'''# -----------------------------------------------
# VPC Network
# -----------------------------------------------
resource "google_compute_network" "vpc" {{
  name                    = "${{var.prefix}}-vpc"
  project                 = var.gcp_project
  auto_create_subnetworks = false
}}

resource "google_compute_subnetwork" "subnet" {{
  name          = "${{var.prefix}}-subnet"
  project       = var.gcp_project
  region        = var.gcp_region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.subnet_cidr
}}

# -----------------------------------------------
# Firewall Rules
# -----------------------------------------------
resource "google_compute_firewall" "allow_ssh" {{
  name    = "${{var.prefix}}-allow-ssh"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {{
    protocol = "tcp"
    ports    = ["22"]
  }}

  source_ranges = var.allowed_source_ranges
  target_tags   = ["${{var.prefix}}-vm"]
}}

resource "google_compute_firewall" "allow_icmp" {{
  name    = "${{var.prefix}}-allow-icmp"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {{
    protocol = "icmp"
  }}

  source_ranges = var.allowed_source_ranges
  target_tags   = ["${{var.prefix}}-vm"]
}}
{extra_firewall}
# -----------------------------------------------
# Static External IP
# -----------------------------------------------
resource "google_compute_address" "static_ip" {{
  name    = "${{var.prefix}}-{os_type}-ip"
  project = var.gcp_project
  region  = var.gcp_region

  labels = var.labels
}}

# -----------------------------------------------
# Compute Instance
# -----------------------------------------------
resource "google_compute_instance" "vm" {{
  name         = "${{var.prefix}}-{os_type}-vm"
  project      = var.gcp_project
  zone         = var.gcp_zone
  machine_type = var.machine_type
  tags         = ["${{var.prefix}}-vm"]

  boot_disk {{
    initialize_params {{
      image = "{boot_disk_image}"
      size  = {boot_disk_size}
      type  = var.disk_type
      labels = var.labels
    }}
  }}

  network_interface {{
    subnetwork = google_compute_subnetwork.subnet.id

    access_config {{
      nat_ip = google_compute_address.static_ip.address
    }}
  }}
{metadata_block}

  labels = var.labels

  service_account {{
    email  = var.service_account_email
    scopes = var.service_account_scopes
  }}

  allow_stopping_for_update = true
}}
''',
        "variables.tf": f'''# -----------------------------------------------
# GCP Project & Region
# -----------------------------------------------
variable "gcp_project" {{
  description = "GCP project ID"
  type        = string
}}

variable "gcp_region" {{
  description = "GCP region"
  type        = string
  default     = "us-central1"
}}

variable "gcp_zone" {{
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}}

# -----------------------------------------------
# Naming & Labels
# -----------------------------------------------
variable "prefix" {{
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}}

variable "labels" {{
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {{
    environment = "dev"
    managed_by  = "terraform"
  }}
}}

# -----------------------------------------------
# Network
# -----------------------------------------------
variable "subnet_cidr" {{
  description = "Subnet CIDR range"
  type        = string
  default     = "10.0.1.0/24"
}}

variable "allowed_source_ranges" {{
  description = "CIDR ranges allowed to access the VM"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}}

# -----------------------------------------------
# Compute Instance
# -----------------------------------------------
variable "machine_type" {{
  description = "GCE machine type"
  type        = string
  default     = "e2-medium"
}}

variable "disk_type" {{
  description = "Boot disk type"
  type        = string
  default     = "pd-balanced"
}}

variable "service_account_email" {{
  description = "Service account email for the instance"
  type        = string
  default     = null
}}

variable "service_account_scopes" {{
  description = "OAuth scopes for the service account"
  type        = list(string)
  default     = ["https://www.googleapis.com/auth/cloud-platform"]
}}
''' + ('''
# -----------------------------------------------
# SSH (Linux)
# -----------------------------------------------
variable "ssh_user" {
  description = "SSH username"
  type        = string
  default     = "admin"
}

variable "ssh_public_key" {
  description = "SSH public key contents"
  type        = string
}
''' if os_type == "linux" else ''),
        "outputs.tf": f'''output "vm_id" {{
  description = "Compute instance ID"
  value       = google_compute_instance.vm.id
}}

output "vm_name" {{
  description = "Compute instance name"
  value       = google_compute_instance.vm.name
}}

output "vm_self_link" {{
  description = "Compute instance self link"
  value       = google_compute_instance.vm.self_link
}}

output "external_ip" {{
  description = "External (public) IP address"
  value       = google_compute_address.static_ip.address
}}

output "internal_ip" {{
  description = "Internal (private) IP address"
  value       = google_compute_instance.vm.network_interface[0].network_ip
}}
{extra_output}''',
        "terraform.tfvars.example": f'''# GCP Project
gcp_project = "my-gcp-project-id"
gcp_region  = "us-central1"
gcp_zone    = "us-central1-a"

# Naming
prefix = "myapp"

labels = {{
  environment = "dev"
  managed_by  = "terraform"
  team        = "platform"
}}

# Network
subnet_cidr           = "10.0.1.0/24"
allowed_source_ranges = ["0.0.0.0/0"]

# Compute
machine_type = "e2-medium"
disk_type    = "pd-balanced"
''' + ('ssh_user       = "admin"\nssh_public_key = "ssh-rsa AAAA...your-key-here"\n'
       if os_type == "linux" else ''),
    }


def _get_kubernetes_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": '''terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
  zone    = var.gcp_zone
}
''',
        "main.tf": '''# -----------------------------------------------
# VPC Network
# -----------------------------------------------
resource "google_compute_network" "vpc" {
  name                    = "${var.prefix}-vpc"
  project                 = var.gcp_project
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.prefix}-subnet"
  project       = var.gcp_project
  region        = var.gcp_region
  network       = google_compute_network.vpc.id
  ip_cidr_range = var.subnet_cidr

  secondary_ip_range {
    range_name    = "${var.prefix}-pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "${var.prefix}-services"
    ip_cidr_range = var.services_cidr
  }
}

# -----------------------------------------------
# GKE Cluster
# -----------------------------------------------
resource "google_container_cluster" "primary" {
  name     = "${var.prefix}-gke"
  project  = var.gcp_project
  location = var.gcp_region

  # We manage node pools separately
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "${var.prefix}-pods"
    services_secondary_range_name = "${var.prefix}-services"
  }

  release_channel {
    channel = var.release_channel
  }

  networking_mode = "VPC_NATIVE"

  private_cluster_config {
    enable_private_nodes    = var.enable_private_nodes
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_cidr
  }

  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_networks
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }

  resource_labels = var.labels
}

# -----------------------------------------------
# Node Pool
# -----------------------------------------------
resource "google_container_node_pool" "primary_nodes" {
  name     = "${var.prefix}-node-pool"
  project  = var.gcp_project
  location = var.gcp_region
  cluster  = google_container_cluster.primary.name

  node_count = var.node_count

  autoscaling {
    min_node_count = var.min_node_count
    max_node_count = var.max_node_count
  }

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = var.node_disk_size_gb
    disk_type    = var.node_disk_type

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    labels = var.labels

    tags = ["${var.prefix}-gke-node"]

    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}
''',
        "variables.tf": '''# -----------------------------------------------
# GCP Project & Region
# -----------------------------------------------
variable "gcp_project" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "gcp_zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

# -----------------------------------------------
# Naming & Labels
# -----------------------------------------------
variable "prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {
    environment = "dev"
    managed_by  = "terraform"
  }
}

# -----------------------------------------------
# Network
# -----------------------------------------------
variable "subnet_cidr" {
  description = "Primary subnet CIDR"
  type        = string
  default     = "10.0.0.0/20"
}

variable "pods_cidr" {
  description = "Secondary range for pods"
  type        = string
  default     = "10.4.0.0/14"
}

variable "services_cidr" {
  description = "Secondary range for services"
  type        = string
  default     = "10.8.0.0/20"
}

# -----------------------------------------------
# GKE Cluster
# -----------------------------------------------
variable "release_channel" {
  description = "GKE release channel (RAPID, REGULAR, STABLE)"
  type        = string
  default     = "REGULAR"
}

variable "enable_private_nodes" {
  description = "Enable private nodes (no external IPs)"
  type        = bool
  default     = true
}

variable "master_cidr" {
  description = "CIDR block for the GKE master"
  type        = string
  default     = "172.16.0.0/28"
}

variable "master_authorized_networks" {
  description = "Networks authorized to access the GKE master"
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = [
    {
      cidr_block   = "0.0.0.0/0"
      display_name = "All"
    }
  ]
}

# -----------------------------------------------
# Node Pool
# -----------------------------------------------
variable "node_count" {
  description = "Initial number of nodes per zone"
  type        = number
  default     = 1
}

variable "min_node_count" {
  description = "Minimum number of nodes for autoscaling"
  type        = number
  default     = 1
}

variable "max_node_count" {
  description = "Maximum number of nodes for autoscaling"
  type        = number
  default     = 5
}

variable "node_machine_type" {
  description = "Machine type for GKE nodes"
  type        = string
  default     = "e2-standard-4"
}

variable "node_disk_size_gb" {
  description = "Disk size per node in GB"
  type        = number
  default     = 100
}

variable "node_disk_type" {
  description = "Disk type for nodes"
  type        = string
  default     = "pd-balanced"
}
''',
        "outputs.tf": '''output "cluster_id" {
  description = "GKE cluster ID"
  value       = google_container_cluster.primary.id
}

output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.primary.name
}

output "cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.primary.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "GKE cluster CA certificate (base64)"
  value       = google_container_cluster.primary.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "kubeconfig_command" {
  description = "gcloud command to configure kubectl"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --region ${var.gcp_region} --project ${var.gcp_project}"
}

output "node_pool_name" {
  description = "Node pool name"
  value       = google_container_node_pool.primary_nodes.name
}
''',
        "terraform.tfvars.example": '''# GCP Project
gcp_project = "my-gcp-project-id"
gcp_region  = "us-central1"
gcp_zone    = "us-central1-a"

# Naming
prefix = "myapp"

labels = {
  environment = "dev"
  managed_by  = "terraform"
  team        = "platform"
}

# Network
subnet_cidr   = "10.0.0.0/20"
pods_cidr     = "10.4.0.0/14"
services_cidr = "10.8.0.0/20"

# GKE Cluster
release_channel      = "REGULAR"
enable_private_nodes = true
master_cidr          = "172.16.0.0/28"

master_authorized_networks = [
  {
    cidr_block   = "10.0.0.0/8"
    display_name = "Internal"
  },
]

# Node Pool
node_count        = 1
min_node_count    = 1
max_node_count    = 5
node_machine_type = "e2-standard-4"
node_disk_size_gb = 100
node_disk_type    = "pd-balanced"
''',
    }


def _get_containers_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": '''terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
}
''',
        "main.tf": '''# -----------------------------------------------
# Cloud Run Service
# -----------------------------------------------
resource "google_cloud_run_v2_service" "default" {
  name     = "${var.prefix}-service"
  project  = var.gcp_project
  location = var.gcp_region
  ingress  = var.ingress_setting

  template {
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.container_image

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = var.cpu_limit
          memory = var.memory_limit
        }
      }

      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.key
          value = env.value
        }
      }

      startup_probe {
        http_get {
          path = var.health_check_path
          port = var.container_port
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = var.health_check_path
          port = var.container_port
        }
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    labels = var.labels

    service_account = var.service_account_email

    timeout = "${var.request_timeout}s"
  }

  labels = var.labels
}

# -----------------------------------------------
# IAM: Allow Public Access (optional)
# -----------------------------------------------
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  count = var.allow_public_access ? 1 : 0

  project  = google_cloud_run_v2_service.default.project
  location = google_cloud_run_v2_service.default.location
  name     = google_cloud_run_v2_service.default.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
''',
        "variables.tf": '''# -----------------------------------------------
# GCP Project & Region
# -----------------------------------------------
variable "gcp_project" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

# -----------------------------------------------
# Naming & Labels
# -----------------------------------------------
variable "prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {
    environment = "dev"
    managed_by  = "terraform"
  }
}

# -----------------------------------------------
# Container Configuration
# -----------------------------------------------
variable "container_image" {
  description = "Container image URI (e.g. gcr.io/project/image:tag)"
  type        = string
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8080
}

variable "cpu_limit" {
  description = "CPU limit (e.g. 1000m, 2)"
  type        = string
  default     = "1000m"
}

variable "memory_limit" {
  description = "Memory limit (e.g. 512Mi, 1Gi)"
  type        = string
  default     = "512Mi"
}

variable "environment_variables" {
  description = "Environment variables for the container"
  type        = map(string)
  default     = {}
}

variable "health_check_path" {
  description = "HTTP path for health checks"
  type        = string
  default     = "/health"
}

variable "request_timeout" {
  description = "Maximum request timeout in seconds"
  type        = number
  default     = 300
}

# -----------------------------------------------
# Scaling
# -----------------------------------------------
variable "min_instances" {
  description = "Minimum number of instances"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 10
}

# -----------------------------------------------
# Networking & Access
# -----------------------------------------------
variable "ingress_setting" {
  description = "Ingress setting (INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER)"
  type        = string
  default     = "INGRESS_TRAFFIC_ALL"
}

variable "allow_public_access" {
  description = "Allow unauthenticated public access"
  type        = bool
  default     = true
}

variable "service_account_email" {
  description = "Service account email for the Cloud Run service"
  type        = string
  default     = null
}
''',
        "outputs.tf": '''output "service_id" {
  description = "Cloud Run service ID"
  value       = google_cloud_run_v2_service.default.id
}

output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.default.name
}

output "service_uri" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.default.uri
}

output "service_location" {
  description = "Cloud Run service location"
  value       = google_cloud_run_v2_service.default.location
}

output "latest_revision" {
  description = "Latest revision name"
  value       = google_cloud_run_v2_service.default.latest_ready_revision
}
''',
        "terraform.tfvars.example": '''# GCP Project
gcp_project = "my-gcp-project-id"
gcp_region  = "us-central1"

# Naming
prefix = "myapp"

labels = {
  environment = "dev"
  managed_by  = "terraform"
  team        = "platform"
}

# Container
container_image = "gcr.io/my-gcp-project-id/my-app:latest"
container_port  = 8080
cpu_limit       = "1000m"
memory_limit    = "512Mi"

environment_variables = {
  APP_ENV  = "production"
  LOG_LEVEL = "info"
}

health_check_path = "/health"
request_timeout   = 300

# Scaling
min_instances = 0
max_instances = 10

# Access
ingress_setting     = "INGRESS_TRAFFIC_ALL"
allow_public_access = true
''',
    }


def _get_networking_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": '''terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
}
''',
        "main.tf": '''# -----------------------------------------------
# VPC Network (Custom Mode)
# -----------------------------------------------
resource "google_compute_network" "vpc" {
  name                    = "${var.prefix}-vpc"
  project                 = var.gcp_project
  auto_create_subnetworks = false
  routing_mode            = var.routing_mode
}

# -----------------------------------------------
# Subnets
# -----------------------------------------------
resource "google_compute_subnetwork" "subnets" {
  for_each = var.subnets

  name          = "${var.prefix}-${each.key}"
  project       = var.gcp_project
  region        = each.value.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = each.value.cidr

  private_ip_google_access = each.value.private_google_access

  dynamic "log_config" {
    for_each = each.value.enable_flow_logs ? [1] : []
    content {
      aggregation_interval = "INTERVAL_5_SEC"
      flow_sampling        = 0.5
      metadata             = "INCLUDE_ALL_METADATA"
    }
  }
}

# -----------------------------------------------
# Firewall Rules
# -----------------------------------------------
resource "google_compute_firewall" "allow_ssh" {
  name    = "${var.prefix}-allow-ssh"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.ssh_source_ranges
  target_tags   = ["${var.prefix}-ssh"]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "allow_http" {
  name    = "${var.prefix}-allow-http"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }

  source_ranges = var.http_source_ranges
  target_tags   = ["${var.prefix}-http"]
}

resource "google_compute_firewall" "allow_https" {
  name    = "${var.prefix}-allow-https"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  source_ranges = var.https_source_ranges
  target_tags   = ["${var.prefix}-https"]
}

resource "google_compute_firewall" "allow_internal" {
  name    = "${var.prefix}-allow-internal"
  network = google_compute_network.vpc.name
  project = var.gcp_project

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = var.internal_ranges
}

# -----------------------------------------------
# Cloud Router
# -----------------------------------------------
resource "google_compute_router" "router" {
  name    = "${var.prefix}-router"
  project = var.gcp_project
  region  = var.gcp_region
  network = google_compute_network.vpc.id

  bgp {
    asn = var.router_asn
  }
}

# -----------------------------------------------
# Cloud NAT
# -----------------------------------------------
resource "google_compute_router_nat" "nat" {
  name    = "${var.prefix}-nat"
  project = var.gcp_project
  region  = var.gcp_region
  router  = google_compute_router.router.name

  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
''',
        "variables.tf": '''# -----------------------------------------------
# GCP Project & Region
# -----------------------------------------------
variable "gcp_project" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "gcp_zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

# -----------------------------------------------
# Naming & Labels
# -----------------------------------------------
variable "prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}

variable "labels" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default = {
    environment = "dev"
    managed_by  = "terraform"
  }
}

# -----------------------------------------------
# VPC
# -----------------------------------------------
variable "routing_mode" {
  description = "VPC routing mode (REGIONAL or GLOBAL)"
  type        = string
  default     = "REGIONAL"
}

# -----------------------------------------------
# Subnets
# -----------------------------------------------
variable "subnets" {
  description = "Subnet configurations"
  type = map(object({
    cidr                  = string
    region                = string
    private_google_access = bool
    enable_flow_logs      = bool
  }))
  default = {
    "public" = {
      cidr                  = "10.0.1.0/24"
      region                = "us-central1"
      private_google_access = false
      enable_flow_logs      = false
    }
    "private" = {
      cidr                  = "10.0.2.0/24"
      region                = "us-central1"
      private_google_access = true
      enable_flow_logs      = true
    }
    "data" = {
      cidr                  = "10.0.3.0/24"
      region                = "us-central1"
      private_google_access = true
      enable_flow_logs      = true
    }
  }
}

# -----------------------------------------------
# Firewall Source Ranges
# -----------------------------------------------
variable "ssh_source_ranges" {
  description = "CIDR ranges allowed SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "http_source_ranges" {
  description = "CIDR ranges allowed HTTP access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "https_source_ranges" {
  description = "CIDR ranges allowed HTTPS access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "internal_ranges" {
  description = "Internal CIDR ranges for unrestricted access"
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

# -----------------------------------------------
# Cloud Router / NAT
# -----------------------------------------------
variable "router_asn" {
  description = "BGP ASN for the Cloud Router"
  type        = number
  default     = 64514
}
''',
        "outputs.tf": '''output "vpc_id" {
  description = "VPC network ID"
  value       = google_compute_network.vpc.id
}

output "vpc_name" {
  description = "VPC network name"
  value       = google_compute_network.vpc.name
}

output "vpc_self_link" {
  description = "VPC network self link"
  value       = google_compute_network.vpc.self_link
}

output "subnet_ids" {
  description = "Map of subnet name to ID"
  value       = { for k, v in google_compute_subnetwork.subnets : k => v.id }
}

output "subnet_self_links" {
  description = "Map of subnet name to self link"
  value       = { for k, v in google_compute_subnetwork.subnets : k => v.self_link }
}

output "subnet_cidrs" {
  description = "Map of subnet name to CIDR range"
  value       = { for k, v in google_compute_subnetwork.subnets : k => v.ip_cidr_range }
}

output "router_id" {
  description = "Cloud Router ID"
  value       = google_compute_router.router.id
}

output "nat_id" {
  description = "Cloud NAT ID"
  value       = google_compute_router_nat.nat.id
}
''',
        "terraform.tfvars.example": '''# GCP Project
gcp_project = "my-gcp-project-id"
gcp_region  = "us-central1"

# Naming
prefix = "myapp"

labels = {
  environment = "dev"
  managed_by  = "terraform"
  team        = "platform"
}

# VPC
routing_mode = "REGIONAL"

# Subnets
subnets = {
  "public" = {
    cidr                  = "10.0.1.0/24"
    region                = "us-central1"
    private_google_access = false
    enable_flow_logs      = false
  }
  "private" = {
    cidr                  = "10.0.2.0/24"
    region                = "us-central1"
    private_google_access = true
    enable_flow_logs      = true
  }
  "data" = {
    cidr                  = "10.0.3.0/24"
    region                = "us-central1"
    private_google_access = true
    enable_flow_logs      = true
  }
}

# Firewall Source Ranges
ssh_source_ranges   = ["203.0.113.0/24"]
http_source_ranges  = ["0.0.0.0/0"]
https_source_ranges = ["0.0.0.0/0"]
internal_ranges     = ["10.0.0.0/8"]

# Cloud Router
router_asn = 64514
''',
    }
