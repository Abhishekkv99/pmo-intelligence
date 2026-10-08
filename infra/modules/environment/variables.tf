# -----------------------------------------------------------------------------
# Identity and placement
# -----------------------------------------------------------------------------

variable "project_name" {
  description = "Project name (pmo-intelligence)"
  type        = string
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
}

variable "short_name" {
  description = "Short prefix for names AWS caps at 32 characters (pmo-staging)"
  type        = string
}

variable "hostname" {
  description = "Public hostname; also the delegated hosted zone and the SES sending domain"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account id (bucket names, ARNs)"
  type        = string
}

# -----------------------------------------------------------------------------
# From the shared stack
# -----------------------------------------------------------------------------

variable "vpc_id" {
  description = "PMO VPC"
  type        = string
}

variable "public_subnet_ids" {
  description = "Subnets for the ALB and the ECS tasks"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Subnets for RDS"
  type        = list(string)
}

variable "ecs_cluster_arn" {
  description = "Shared ECS cluster"
  type        = string
}

variable "ecr_repository_urls" {
  description = "Repository URL per image: { backend = ..., frontend = ... }"
  type        = map(string)
}

# -----------------------------------------------------------------------------
# ECS
# -----------------------------------------------------------------------------

variable "image_tag" {
  description = "Image tag the services run; CI moves it on every deploy (staging-latest)"
  type        = string
}

variable "backend_cpu" {
  description = "Backend task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "backend_memory" {
  description = "Backend task memory in MiB (II needed 1024 after OOM kills at 512)"
  type        = number
  default     = 1024
}

variable "frontend_cpu" {
  description = "Frontend task CPU units"
  type        = number
  default     = 256
}

variable "frontend_memory" {
  description = "Frontend task memory in MiB"
  type        = number
  default     = 512
}

variable "backend_desired_count" {
  description = "Backend tasks"
  type        = number
  default     = 1
}

variable "frontend_desired_count" {
  description = "Frontend tasks"
  type        = number
  default     = 1
}

variable "processing_concurrency" {
  description = "Processing-queue workers (PROCESSING_CONCURRENCY)"
  type        = number
  default     = 1
}

variable "bootstrap_admin_emails" {
  description = "Comma-separated emails raised to pmo_manager at startup (BOOTSTRAP_ADMIN_EMAILS); not secret"
  type        = string
  default     = ""
}

variable "azure_openai_api_version" {
  description = "Azure OpenAI API version (AZURE_OPENAI_API_VERSION); not secret"
  type        = string
  default     = "2025-04-01-preview"
}

variable "log_retention_days" {
  description = "CloudWatch log retention"
  type        = number
  default     = 14
}

# -----------------------------------------------------------------------------
# RDS
# -----------------------------------------------------------------------------

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS storage in GB (gp3)"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database created with the instance; the app's pmo_app role owns it after the db bootstrap"
  type        = string
  default     = "pmo_intelligence"
}

variable "db_master_username" {
  description = "RDS master user (password managed by RDS in Secrets Manager)"
  type        = string
  default     = "postgres"
}

variable "db_backup_retention_days" {
  description = "Automated backup retention"
  type        = number
  default     = 7
}

variable "recordings_source_bucket" {
  description = "Bucket holding the PMO call recordings (main ITC account; read through its bucket policy)"
  type        = string
  default     = "nextcloud-talk-recordings-itc"
}

variable "recordings_source_prefix" {
  description = "Prefix of the PMO recordings folder in that bucket, with its trailing slash"
  type        = string
  default     = "recordings/pmo/"
}

variable "recordings_scan_enabled" {
  description = "Catalog the recordings folder every 15 minutes (RECORDINGS_SCAN_ENABLED); never processes"
  type        = bool
  default     = false
}
