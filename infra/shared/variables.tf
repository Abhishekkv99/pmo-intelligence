variable "aws_region" {
  description = "AWS region for every shared resource"
  type        = string
  default     = "eu-west-2"
}

variable "aws_account_id" {
  description = "The only AWS account this stack may run against (ITC Sandbox PD Intelligence)"
  type        = string
  default     = "260172548683"
}

variable "project_name" {
  description = "Project name, used in resource names and tags"
  type        = string
  default     = "pmo-intelligence"
}

variable "github_repo" {
  description = "GitHub repository (owner/name) whose workflows may assume the deploy role"
  type        = string
  default     = "Abhishekkv99/pmo-intelligence"
}

variable "github_deploy_branches" {
  description = "Branches whose workflow runs may assume the deploy role (develop deploys staging; main is added with production)"
  type        = list(string)
  default     = ["develop"]
}

# -----------------------------------------------------------------------------
# Network
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for PMO's VPC; clear of the default VPC and II's 10.0.0.0/16"
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Availability zones to spread subnets across (an ALB needs two)"
  type        = number
  default     = 2
}

# -----------------------------------------------------------------------------
# ECR
# -----------------------------------------------------------------------------

variable "ecr_untagged_expiry_days" {
  description = "Days before an untagged image expires"
  type        = number
  default     = 7
}

variable "ecr_tagged_images_kept" {
  description = "Tagged images (sha-, staging-, latest) kept per repository"
  type        = number
  default     = 10
}
