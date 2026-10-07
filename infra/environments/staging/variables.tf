variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-2"
}

variable "aws_account_id" {
  description = "The only AWS account this stack may run against (ITC Sandbox PD Intelligence)"
  type        = string
  default     = "260172548683"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "pmo-intelligence"
}

variable "bootstrap_admin_emails" {
  description = "Comma-separated emails raised to pmo_manager at startup; set in terraform.tfvars (not committed)"
  type        = string
  default     = ""
}
