terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    bucket       = "pmo-intelligence-tfstate-260172548683"
    key          = "shared/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
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
      Stack     = "shared"
    }
  }
}
