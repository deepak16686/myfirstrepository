"""
File: aws.py
Purpose: Provides hardcoded default Terraform HCL templates for AWS infrastructure, covering EC2 instances (Linux/Windows), EKS clusters with managed node groups, ECS Fargate services with ALB, and VPC networking with public/private subnets and NAT Gateway.
When Used: Called by the default_templates dispatcher when the user selects AWS as the provider and no ChromaDB or LLM-generated template is available.
Why Created: Ensures the Terraform generator always has a working baseline template for every AWS resource type, even when ChromaDB is empty and the LLM is unavailable or produces invalid output.
"""
from typing import Dict, Optional


def get_aws_template(resource_type: str, sub_type: Optional[str] = None) -> Dict[str, str]:
    """Dispatch to resource-specific AWS template."""
    templates = {
        "vm": _get_vm_template,
        "kubernetes": _get_kubernetes_template,
        "containers": _get_containers_template,
        "networking": _get_networking_template,
    }
    handler = templates.get(resource_type)
    if not handler:
        raise ValueError(f"Unknown resource type for AWS: {resource_type}")
    return handler(sub_type)


# ---------------------------------------------------------------------------
# Common provider block shared across all templates
# ---------------------------------------------------------------------------
_PROVIDER_TF = '''terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key

  default_tags {
    tags = var.tags
  }
}
'''

# ---------------------------------------------------------------------------
# Common variables included in every template
# ---------------------------------------------------------------------------
_COMMON_VARIABLES = '''# AWS Connection
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_access_key" {
  description = "AWS access key"
  type        = string
  sensitive   = true
}

variable "aws_secret_key" {
  description = "AWS secret key"
  type        = string
  sensitive   = true
}

# Naming / Tagging
variable "prefix" {
  description = "Resource name prefix"
  type        = string
  default     = "myapp"
}

variable "tags" {
  description = "Default tags applied to all resources"
  type        = map(string)
  default = {
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}
'''


# ---------------------------------------------------------------------------
# VM (EC2) Template
# ---------------------------------------------------------------------------
def _get_vm_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    os_type = sub_type or "linux"
    is_windows = os_type == "windows"

    if is_windows:
        ami_filter = 'Windows_Server-2022-English-Full-Base-*'
        ami_owner = "801119661308"  # Amazon / Microsoft
        ami_description = "Latest Windows Server 2022 AMI"
        default_instance_type = "t3.large"
        default_disk_gb = 100
    else:
        ami_filter = 'al2023-ami-2023.*-x86_64'
        ami_owner = "137112412989"  # Amazon
        ami_description = "Latest Amazon Linux 2023 AMI"
        default_instance_type = "t3.medium"
        default_disk_gb = 30

    windows_extra_resource = """
  get_password_data = true
""" if is_windows else ""

    windows_extra_output = """
output "instance_password_data" {
  description = "Encrypted password data (decrypt with private key)"
  value       = aws_instance.vm.password_data
  sensitive   = true
}
""" if is_windows else ""

    return {
        "provider.tf": _PROVIDER_TF,

        "main.tf": f'''# -----------------------------------------------------------
# VPC & Networking
# -----------------------------------------------------------
resource "aws_vpc" "main" {{
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {{
    Name = "${{var.prefix}}-vpc"
  }}
}}

resource "aws_subnet" "public" {{
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.subnet_cidr
  availability_zone       = "${{var.aws_region}}a"
  map_public_ip_on_launch = true

  tags = {{
    Name = "${{var.prefix}}-public-subnet"
  }}
}}

resource "aws_internet_gateway" "gw" {{
  vpc_id = aws_vpc.main.id

  tags = {{
    Name = "${{var.prefix}}-igw"
  }}
}}

resource "aws_route_table" "public" {{
  vpc_id = aws_vpc.main.id

  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }}

  tags = {{
    Name = "${{var.prefix}}-public-rt"
  }}
}}

resource "aws_route_table_association" "public" {{
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}}

# -----------------------------------------------------------
# Security Group
# -----------------------------------------------------------
resource "aws_security_group" "vm" {{
  name_prefix = "${{var.prefix}}-vm-"
  description = "Security group for ${{var.prefix}} {"Windows" if is_windows else "Linux"} VM"
  vpc_id      = aws_vpc.main.id

  {"ingress {" if is_windows else "ingress {"}
    description = "{"RDP" if is_windows else "SSH"} access"
    from_port   = {"3389" if is_windows else "22"}
    to_port     = {"3389" if is_windows else "22"}
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
  }}

  ingress {{
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  ingress {{
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  egress {{
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = {{
    Name = "${{var.prefix}}-vm-sg"
  }}
}}

# -----------------------------------------------------------
# Key Pair
# -----------------------------------------------------------
resource "aws_key_pair" "deployer" {{
  key_name   = "${{var.prefix}}-deployer-key"
  public_key = var.public_key

  tags = {{
    Name = "${{var.prefix}}-deployer-key"
  }}
}}

# -----------------------------------------------------------
# AMI Data Source
# -----------------------------------------------------------
data "aws_ami" "selected" {{
  most_recent = true
  owners      = ["{ami_owner}"]

  filter {{
    name   = "name"
    values = ["{ami_filter}"]
  }}

  filter {{
    name   = "virtualization-type"
    values = ["hvm"]
  }}

  filter {{
    name   = "architecture"
    values = ["x86_64"]
  }}
}}

# -----------------------------------------------------------
# EC2 Instance
# -----------------------------------------------------------
resource "aws_instance" "vm" {{
  ami                    = data.aws_ami.selected.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.vm.id]
  key_name               = aws_key_pair.deployer.key_name
{windows_extra_resource}
  root_block_device {{
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }}

  tags = {{
    Name = "${{var.prefix}}-{os_type}-vm"
  }}
}}
''',

        "variables.tf": _COMMON_VARIABLES + f'''
# VPC
variable "vpc_cidr" {{
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}}

variable "subnet_cidr" {{
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}}

# EC2 Instance
variable "instance_type" {{
  description = "EC2 instance type"
  type        = string
  default     = "{default_instance_type}"
}}

variable "root_volume_size" {{
  description = "Root volume size in GB"
  type        = number
  default     = {default_disk_gb}
}}

variable "public_key" {{
  description = "SSH public key for the key pair"
  type        = string
}}

variable "allowed_ssh_cidrs" {{
  description = "CIDR blocks allowed {"RDP" if is_windows else "SSH"} access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}}
''',

        "outputs.tf": f'''output "instance_id" {{
  description = "EC2 instance ID"
  value       = aws_instance.vm.id
}}

output "instance_public_ip" {{
  description = "Public IP address of the instance"
  value       = aws_instance.vm.public_ip
}}

output "instance_public_dns" {{
  description = "Public DNS name of the instance"
  value       = aws_instance.vm.public_dns
}}

output "instance_private_ip" {{
  description = "Private IP address of the instance"
  value       = aws_instance.vm.private_ip
}}

output "ami_id" {{
  description = "{ami_description} used"
  value       = data.aws_ami.selected.id
}}

output "vpc_id" {{
  description = "VPC ID"
  value       = aws_vpc.main.id
}}

output "security_group_id" {{
  description = "Security group ID"
  value       = aws_security_group.vm.id
}}
{windows_extra_output}''',

        "terraform.tfvars.example": f'''# AWS Connection
aws_region     = "us-east-1"
aws_access_key = "YOUR_AWS_ACCESS_KEY"
aws_secret_key = "YOUR_AWS_SECRET_KEY"

# Naming
prefix = "myapp"

# VPC
vpc_cidr    = "10.0.0.0/16"
subnet_cidr = "10.0.1.0/24"

# EC2 Instance
instance_type    = "{default_instance_type}"
root_volume_size = {default_disk_gb}
public_key       = "ssh-rsa AAAA...your-public-key..."
allowed_ssh_cidrs = ["YOUR_IP/32"]

# Tags
tags = {{
  Environment = "dev"
  ManagedBy   = "terraform"
}}
''',
    }


# ---------------------------------------------------------------------------
# Kubernetes (EKS) Template
# ---------------------------------------------------------------------------
def _get_kubernetes_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,

        "main.tf": '''# -----------------------------------------------------------
# VPC & Networking
# -----------------------------------------------------------
resource "aws_vpc" "eks" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name                                        = "${var.prefix}-eks-vpc"
    "kubernetes.io/cluster/${var.prefix}-cluster" = "shared"
  }
}

resource "aws_subnet" "eks_private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.eks.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name                                        = "${var.prefix}-eks-private-${count.index + 1}"
    "kubernetes.io/cluster/${var.prefix}-cluster" = "shared"
    "kubernetes.io/role/internal-elb"            = "1"
  }
}

resource "aws_subnet" "eks_public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.eks.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name                                        = "${var.prefix}-eks-public-${count.index + 1}"
    "kubernetes.io/cluster/${var.prefix}-cluster" = "shared"
    "kubernetes.io/role/elb"                     = "1"
  }
}

resource "aws_internet_gateway" "eks" {
  vpc_id = aws_vpc.eks.id

  tags = {
    Name = "${var.prefix}-eks-igw"
  }
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.prefix}-eks-nat-eip"
  }
}

resource "aws_nat_gateway" "eks" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.eks_public[0].id

  tags = {
    Name = "${var.prefix}-eks-nat"
  }

  depends_on = [aws_internet_gateway.eks]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.eks.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.eks.id
  }

  tags = {
    Name = "${var.prefix}-eks-public-rt"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.eks.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.eks.id
  }

  tags = {
    Name = "${var.prefix}-eks-private-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(var.public_subnet_cidrs)
  subnet_id      = aws_subnet.eks_public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(var.private_subnet_cidrs)
  subnet_id      = aws_subnet.eks_private[count.index].id
  route_table_id = aws_route_table.private.id
}

# -----------------------------------------------------------
# IAM Roles
# -----------------------------------------------------------
resource "aws_iam_role" "eks_cluster" {
  name = "${var.prefix}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.prefix}-eks-cluster-role"
  }
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role" "eks_nodes" {
  name = "${var.prefix}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.prefix}-eks-node-role"
  }
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "ecr_read_only" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

# -----------------------------------------------------------
# EKS Cluster
# -----------------------------------------------------------
resource "aws_eks_cluster" "main" {
  name     = "${var.prefix}-cluster"
  version  = var.kubernetes_version
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids              = concat(aws_subnet.eks_private[*].id, aws_subnet.eks_public[*].id)
    endpoint_private_access = true
    endpoint_public_access  = var.cluster_endpoint_public_access
  }

  tags = {
    Name = "${var.prefix}-cluster"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_resource_controller,
  ]
}

# -----------------------------------------------------------
# EKS Node Group
# -----------------------------------------------------------
resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.prefix}-default-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.eks_private[*].id

  instance_types = var.node_instance_types
  disk_size      = var.node_disk_size

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  tags = {
    Name = "${var.prefix}-default-nodes"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.ecr_read_only,
  ]
}
''',

        "variables.tf": _COMMON_VARIABLES + '''
# VPC
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# EKS Cluster
variable "kubernetes_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.29"
}

variable "cluster_endpoint_public_access" {
  description = "Enable public access to the cluster API endpoint"
  type        = bool
  default     = true
}

# Node Group
variable "node_instance_types" {
  description = "Instance types for the default node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_disk_size" {
  description = "Disk size in GB for worker nodes"
  type        = number
  default     = 50
}

variable "node_desired_size" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 5
}
''',

        "outputs.tf": '''output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "cluster_certificate_authority" {
  description = "Base64 encoded cluster CA certificate"
  value       = aws_eks_cluster.main.certificate_authority[0].data
  sensitive   = true
}

output "cluster_version" {
  description = "Kubernetes version"
  value       = aws_eks_cluster.main.version
}

output "cluster_security_group_id" {
  description = "Security group ID attached to the EKS cluster"
  value       = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
}

output "node_group_name" {
  description = "Name of the default node group"
  value       = aws_eks_node_group.default.node_group_name
}

output "node_group_status" {
  description = "Status of the default node group"
  value       = aws_eks_node_group.default.status
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.eks.id
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name}"
}
''',

        "terraform.tfvars.example": '''# AWS Connection
aws_region     = "us-east-1"
aws_access_key = "YOUR_AWS_ACCESS_KEY"
aws_secret_key = "YOUR_AWS_SECRET_KEY"

# Naming
prefix = "myapp"

# VPC
vpc_cidr             = "10.0.0.0/16"
availability_zones   = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

# EKS Cluster
kubernetes_version             = "1.29"
cluster_endpoint_public_access = true

# Node Group
node_instance_types = ["t3.medium"]
node_disk_size      = 50
node_desired_size   = 2
node_min_size       = 1
node_max_size       = 5

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }


# ---------------------------------------------------------------------------
# Containers (ECS Fargate) Template
# ---------------------------------------------------------------------------
def _get_containers_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,

        "main.tf": '''# -----------------------------------------------------------
# VPC & Networking
# -----------------------------------------------------------
resource "aws_vpc" "ecs" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.prefix}-ecs-vpc"
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.ecs.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.prefix}-ecs-public-${count.index + 1}"
  }
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.ecs.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "${var.prefix}-ecs-private-${count.index + 1}"
  }
}

resource "aws_internet_gateway" "ecs" {
  vpc_id = aws_vpc.ecs.id

  tags = {
    Name = "${var.prefix}-ecs-igw"
  }
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.prefix}-ecs-nat-eip"
  }
}

resource "aws_nat_gateway" "ecs" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "${var.prefix}-ecs-nat"
  }

  depends_on = [aws_internet_gateway.ecs]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.ecs.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ecs.id
  }

  tags = {
    Name = "${var.prefix}-ecs-public-rt"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.ecs.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.ecs.id
  }

  tags = {
    Name = "${var.prefix}-ecs-private-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(var.public_subnet_cidrs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(var.private_subnet_cidrs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# -----------------------------------------------------------
# Security Groups
# -----------------------------------------------------------
resource "aws_security_group" "alb" {
  name_prefix = "${var.prefix}-alb-"
  description = "Security group for the Application Load Balancer"
  vpc_id      = aws_vpc.ecs.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.prefix}-alb-sg"
  }
}

resource "aws_security_group" "ecs_tasks" {
  name_prefix = "${var.prefix}-ecs-tasks-"
  description = "Security group for ECS Fargate tasks"
  vpc_id      = aws_vpc.ecs.id

  ingress {
    description     = "Allow traffic from ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.prefix}-ecs-tasks-sg"
  }
}

# -----------------------------------------------------------
# Application Load Balancer
# -----------------------------------------------------------
resource "aws_lb" "main" {
  name               = "${var.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false

  tags = {
    Name = "${var.prefix}-alb"
  }
}

resource "aws_lb_target_group" "app" {
  name        = "${var.prefix}-tg"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.ecs.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 3
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = var.health_check_path
    protocol            = "HTTP"
    matcher             = "200-299"
  }

  tags = {
    Name = "${var.prefix}-tg"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# -----------------------------------------------------------
# ECS Cluster & Service
# -----------------------------------------------------------
resource "aws_ecs_cluster" "main" {
  name = "${var.prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.prefix}-cluster"
  }
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.prefix}"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.prefix}-ecs-logs"
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${var.prefix}-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "${var.prefix}-app"
    image     = var.container_image
    essential = true

    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    environment = [
      for k, v in var.environment_variables : {
        name  = k
        value = v
      }
    ]
  }])

  tags = {
    Name = "${var.prefix}-task-def"
  }
}

resource "aws_ecs_service" "app" {
  name            = "${var.prefix}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.service_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "${var.prefix}-app"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.http]

  tags = {
    Name = "${var.prefix}-service"
  }
}

# -----------------------------------------------------------
# IAM Roles for ECS
# -----------------------------------------------------------
resource "aws_iam_role" "ecs_execution" {
  name = "${var.prefix}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.prefix}-ecs-execution-role"
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.prefix}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.prefix}-ecs-task-role"
  }
}
''',

        "variables.tf": _COMMON_VARIABLES + '''
# VPC
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# Container
variable "container_image" {
  description = "Docker image for the ECS task"
  type        = string
  default     = "nginx:latest"
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
  default     = 80
}

variable "health_check_path" {
  description = "Health check path for the target group"
  type        = string
  default     = "/"
}

# Task Definition
variable "task_cpu" {
  description = "CPU units for the Fargate task (1024 = 1 vCPU)"
  type        = string
  default     = "256"
}

variable "task_memory" {
  description = "Memory in MB for the Fargate task"
  type        = string
  default     = "512"
}

# Service
variable "service_desired_count" {
  description = "Desired number of running tasks"
  type        = number
  default     = 2
}

variable "environment_variables" {
  description = "Environment variables for the container"
  type        = map(string)
  default     = {}
}

# Logging
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}
''',

        "outputs.tf": '''output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.app.name
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = aws_lb.main.zone_id
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.main.arn
}

output "target_group_arn" {
  description = "ARN of the target group"
  value       = aws_lb_target_group.app.arn
}

output "task_definition_arn" {
  description = "ARN of the task definition"
  value       = aws_ecs_task_definition.app.arn
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.ecs.id
}

output "app_url" {
  description = "Application URL via ALB"
  value       = "http://${aws_lb.main.dns_name}"
}
''',

        "terraform.tfvars.example": '''# AWS Connection
aws_region     = "us-east-1"
aws_access_key = "YOUR_AWS_ACCESS_KEY"
aws_secret_key = "YOUR_AWS_SECRET_KEY"

# Naming
prefix = "myapp"

# VPC
vpc_cidr             = "10.0.0.0/16"
availability_zones   = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

# Container
container_image = "nginx:latest"
container_port  = 80

# Task Definition
task_cpu    = "256"
task_memory = "512"

# Service
service_desired_count = 2
health_check_path     = "/"

# Logging
log_retention_days = 30

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }


# ---------------------------------------------------------------------------
# Networking (VPC with Public/Private Subnets, NAT GW) Template
# ---------------------------------------------------------------------------
def _get_networking_template(sub_type: Optional[str] = None) -> Dict[str, str]:
    return {
        "provider.tf": _PROVIDER_TF,

        "main.tf": '''# -----------------------------------------------------------
# VPC
# -----------------------------------------------------------
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.prefix}-vpc"
  }
}

# -----------------------------------------------------------
# Public Subnets (2 AZs)
# -----------------------------------------------------------
resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.prefix}-public-subnet-${count.index + 1}"
  }
}

# -----------------------------------------------------------
# Private Subnets (2 AZs)
# -----------------------------------------------------------
resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "${var.prefix}-private-subnet-${count.index + 1}"
  }
}

# -----------------------------------------------------------
# Internet Gateway
# -----------------------------------------------------------
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.prefix}-igw"
  }
}

# -----------------------------------------------------------
# NAT Gateway (with Elastic IP)
# -----------------------------------------------------------
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.prefix}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "${var.prefix}-nat-gw"
  }

  depends_on = [aws_internet_gateway.main]
}

# -----------------------------------------------------------
# Route Tables
# -----------------------------------------------------------

# Public route table — routes to Internet Gateway
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(var.public_subnet_cidrs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private route table — routes to NAT Gateway
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = {
    Name = "${var.prefix}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  count          = length(var.private_subnet_cidrs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# -----------------------------------------------------------
# Security Group — General Purpose
# -----------------------------------------------------------
resource "aws_security_group" "general" {
  name_prefix = "${var.prefix}-general-"
  description = "General-purpose security group"
  vpc_id      = aws_vpc.main.id

  # SSH
  ingress {
    description = "SSH access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
  }

  # HTTP
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # HTTPS
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # ICMP (ping)
  ingress {
    description = "ICMP ping"
    from_port   = -1
    to_port     = -1
    protocol    = "icmp"
    cidr_blocks = [var.vpc_cidr]
  }

  # All outbound
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.prefix}-general-sg"
  }
}

# -----------------------------------------------------------
# Security Group — Database (private subnets only)
# -----------------------------------------------------------
resource "aws_security_group" "database" {
  name_prefix = "${var.prefix}-db-"
  description = "Security group for databases in private subnets"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from general SG"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.general.id]
  }

  ingress {
    description     = "MySQL from general SG"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.general.id]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.prefix}-db-sg"
  }
}
''',

        "variables.tf": _COMMON_VARIABLES + '''
# VPC
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnets (minimum 2)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# Security
variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
''',

        "outputs.tf": '''output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks"
  value       = aws_subnet.public[*].cidr_block
}

output "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks"
  value       = aws_subnet.private[*].cidr_block
}

output "internet_gateway_id" {
  description = "Internet Gateway ID"
  value       = aws_internet_gateway.main.id
}

output "nat_gateway_id" {
  description = "NAT Gateway ID"
  value       = aws_nat_gateway.main.id
}

output "nat_gateway_public_ip" {
  description = "NAT Gateway public IP"
  value       = aws_eip.nat.public_ip
}

output "public_route_table_id" {
  description = "Public route table ID"
  value       = aws_route_table.public.id
}

output "private_route_table_id" {
  description = "Private route table ID"
  value       = aws_route_table.private.id
}

output "general_security_group_id" {
  description = "General-purpose security group ID"
  value       = aws_security_group.general.id
}

output "database_security_group_id" {
  description = "Database security group ID"
  value       = aws_security_group.database.id
}
''',

        "terraform.tfvars.example": '''# AWS Connection
aws_region     = "us-east-1"
aws_access_key = "YOUR_AWS_ACCESS_KEY"
aws_secret_key = "YOUR_AWS_SECRET_KEY"

# Naming
prefix = "myapp"

# VPC
vpc_cidr             = "10.0.0.0/16"
availability_zones   = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]

# Security
allowed_ssh_cidrs = ["YOUR_IP/32"]

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
}
''',
    }
