# -----------------------------------------------------------------------------
# PMO's Azure OpenAI: its own resource group and resource (nothing shared with
# Interview Intelligence), so cost, keys, RBAC and lifecycle are PMO's alone.
# Environments are separate deployments on the one resource.
# Note: TPM quota is per subscription, region, model and deployment type, so it
# is shared with any other Data Zone deployment of the same model in this
# subscription and region.
# -----------------------------------------------------------------------------

locals {
  name = "${var.project_name}-${var.location_short}" # pmo-intelligence-swc

  tags = {
    project    = var.project_name
    managed-by = "terraform"
  }

  # { "staging-chat" = {...}, "staging-embedding" = {...} }
  deployments = merge([
    for env, cfg in var.environments : {
      "${env}-chat" = {
        name     = "${var.chat_model.name}-${env}"
        model    = var.chat_model
        capacity = cfg.chat_capacity
        env      = env
      }
      "${env}-embedding" = {
        name     = "${var.embedding_model.name}-${env}"
        model    = var.embedding_model
        capacity = cfg.embedding_capacity
        env      = env
      }
    }
  ]...)
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_cognitive_account" "openai" {
  name                = "oai-${local.name}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  kind                = "OpenAI"
  sku_name            = "S0"

  # Endpoint https://oai-pmo-intelligence-swc.openai.azure.com/
  custom_subdomain_name = "oai-${local.name}"

  # The app authenticates with an API key (AZURE_OPENAI_API_KEY) from the
  # internet-facing ECS tasks
  local_auth_enabled            = true
  public_network_access_enabled = true

  tags = local.tags
}

resource "azurerm_cognitive_deployment" "this" {
  for_each = local.deployments

  name                 = each.value.name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = each.value.model.name
    version = each.value.model.version
  }

  sku {
    name     = var.deployment_sku
    capacity = each.value.capacity
  }

  # Model versions are pinned; Azure must not swap them underneath the app
  version_upgrade_option = "NoAutoUpgrade"
}
