terraform {
  required_version = ">= 1.10"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
    }
  }

  # State sits with the AWS stacks (needs AWS_PROFILE=pmo-intelligence)
  backend "s3" {
    bucket       = "pmo-intelligence-tfstate-260172548683"
    key          = "azure/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

# Credentials come from the Azure CLI login (az login)
provider "azurerm" {
  features {}

  # Pinned so a different default subscription in az cannot be targeted
  subscription_id = var.subscription_id
}
