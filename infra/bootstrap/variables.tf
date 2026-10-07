variable "aws_region" {
  description = "AWS region for the state bucket"
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

variable "noncurrent_version_retention_days" {
  description = "Days an overwritten state version is kept before it expires"
  type        = number
  default     = 90
}
