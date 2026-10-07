# -----------------------------------------------------------------------------
# App secret: one JSON object; task definitions read single keys with
# valueFrom "<arn>:<KEY>::". Created with placeholders; real values are set
# outside Terraform (aws secretsmanager put-secret-value, never in chat or
# git), and Terraform then leaves the value alone. DATABASE_URL is written by
# the db bootstrap once pmo_app exists.
# -----------------------------------------------------------------------------

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

locals {
  # Every key the backend reads from the secret; anything not secret is a
  # plain environment variable in ecs.tf
  app_secret_keys = [
    "DATABASE_URL",
    "SECRET_KEY",
    "ASSEMBLYAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_EMBEDDING_DEPLOYMENT",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "AZURE_ALLOWED_TENANT_IDS",
  ]
}

resource "aws_secretsmanager_secret" "app" {
  name        = "${var.project_name}/${var.environment}/app"
  description = "Application secrets for ${local.name}"

  recovery_window_in_days = 30

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    DATABASE_URL               = "SET_BY_DB_BOOTSTRAP"
    SECRET_KEY                 = random_password.secret_key.result
    ASSEMBLYAI_API_KEY         = "CHANGE_ME"
    AZURE_OPENAI_API_KEY       = "CHANGE_ME"
    AZURE_OPENAI_ENDPOINT      = "CHANGE_ME"
    AZURE_OPENAI_DEPLOYMENT    = "CHANGE_ME"
    AZURE_EMBEDDING_DEPLOYMENT = "CHANGE_ME"
    AZURE_CLIENT_ID            = "CHANGE_ME"
    AZURE_CLIENT_SECRET        = "CHANGE_ME"
    AZURE_TENANT_ID            = "CHANGE_ME"
    AZURE_ALLOWED_TENANT_IDS   = ""
  })

  lifecycle {
    # Real values are set by hand after the first apply; never revert them
    ignore_changes = [secret_string]
  }
}
