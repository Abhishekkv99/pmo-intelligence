output "resource_group" {
  description = "PMO's Azure resource group (cost tracking scope)"
  value       = azurerm_resource_group.this.name
}

output "openai_account" {
  description = "Azure OpenAI resource"
  value       = azurerm_cognitive_account.openai.name
}

output "openai_endpoint" {
  description = "AZURE_OPENAI_ENDPOINT"
  value       = azurerm_cognitive_account.openai.endpoint
}

# AZURE_OPENAI_DEPLOYMENT and AZURE_EMBEDDING_DEPLOYMENT per environment
output "deployments" {
  description = "Deployment names per environment"
  value = {
    for env in keys(var.environments) : env => {
      AZURE_OPENAI_DEPLOYMENT    = azurerm_cognitive_deployment.this["${env}-chat"].name
      AZURE_EMBEDDING_DEPLOYMENT = azurerm_cognitive_deployment.this["${env}-embedding"].name
    }
  }
}

# The API key is not an output; read it with
#   az cognitiveservices account keys list -g <resource_group> -n <openai_account>
