variable "subscription_id" {
  description = "Azure subscription that holds PMO's Azure resources"
  type        = string
  default     = "3a72be92-287b-4f1e-840a-5e3e71100139"
}

variable "location" {
  description = "Azure region; Sweden Central offers Data Zone Standard (EU processing) for the models used"
  type        = string
  default     = "swedencentral"
}

variable "location_short" {
  description = "Region suffix used in names"
  type        = string
  default     = "swc"
}

variable "project_name" {
  description = "Project name, used in resource names and tags"
  type        = string
  default     = "pmo-intelligence"
}

variable "deployment_sku" {
  description = "Deployment type; DataZoneStandard keeps prompt processing inside the EU data zone"
  type        = string
  default     = "DataZoneStandard"
}

variable "chat_model" {
  description = "Chat model for the session and chat pipelines"
  type = object({
    name    = string
    version = string
  })
  default = {
    name    = "gpt-5.4-mini"
    version = "2026-03-17"
  }
}

variable "embedding_model" {
  description = "Embedding model; 1536 dimensions to match signals.embedding"
  type = object({
    name    = string
    version = string
  })
  default = {
    name    = "text-embedding-3-small"
    version = "1"
  }
}

# One resource serves every environment; each gets its own deployments, so its
# capacity is capped separately. Capacity is in thousands of tokens per minute.
variable "environments" {
  description = "Per-environment deployment capacity (thousands of tokens per minute)"
  type = map(object({
    chat_capacity      = number
    embedding_capacity = number
  }))
  default = {
    staging = {
      chat_capacity      = 50
      embedding_capacity = 50
    }
  }
}

variable "rg_creation_policy_assignment_id" {
  description = "Subscription policy that denies creating or updating resource groups outside managed-service name patterns"
  type        = string
  default     = "/subscriptions/3a72be92-287b-4f1e-840a-5e3e71100139/providers/Microsoft.Authorization/policyAssignments/110d1e5c334d45929d8e2412"
}
