terraform {
  # use_lockfile (native S3 state locking) needs 1.10 or later
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Credentials come from the environment: AWS_PROFILE=pmo-intelligence (SSO).
provider "aws" {
  region = var.aws_region

  # Refuse to touch any account other than PMO's sandbox
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}
