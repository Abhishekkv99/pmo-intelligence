output "url" {
  description = "Staging URL"
  value       = module.environment.url
}

output "hosted_zone_name_servers" {
  description = "Give these to whoever manages itcapp.ai: one NS record for pmo-intelligence-staging.itcapp.ai"
  value       = module.environment.hosted_zone_name_servers
}

output "alb_dns_name" {
  description = "Staging ALB"
  value       = module.environment.alb_dns_name
}

output "app_secret_arn" {
  description = "Staging app secret; fill its CHANGE_ME values with aws secretsmanager put-secret-value"
  value       = module.environment.app_secret_arn
}

output "db_endpoint" {
  description = "Staging RDS endpoint"
  value       = module.environment.db_endpoint
}

output "db_master_secret_arn" {
  description = "RDS-managed master credentials (db bootstrap only)"
  value       = module.environment.db_master_secret_arn
}

output "media_bucket" {
  description = "Staging media bucket"
  value       = module.environment.media_bucket
}

output "ses_identity" {
  description = "SES sending domain"
  value       = module.environment.ses_identity
}

# Values for the GitHub repository variables the deploy-staging job reads
output "github_variables" {
  description = "Set these as repository variables (Settings > Secrets and variables > Actions > Variables)"
  value = {
    AWS_ROLE_ARN                 = local.shared.github_deploy_role_arn
    AWS_REGION                   = local.shared.aws_region
    ECR_REGISTRY                 = local.shared.ecr_registry
    ECS_CLUSTER_NAME             = local.shared.ecs_cluster_name
    ECS_STAGING_BACKEND_SERVICE  = module.environment.backend_service_name
    ECS_STAGING_FRONTEND_SERVICE = module.environment.frontend_service_name
  }
}

# Read by scripts/db-bootstrap.sh
output "ecs_cluster_name" {
  description = "ECS cluster"
  value       = local.shared.ecs_cluster_name
}

output "db_bootstrap_task_definition" {
  description = "Task definition ARN of the database bootstrap"
  value       = module.environment.db_bootstrap_task_definition
}

output "db_bootstrap_subnets" {
  description = "Subnets for the bootstrap task, comma-separated"
  value       = module.environment.db_bootstrap_subnets
}

output "db_bootstrap_security_group" {
  description = "Security group for the bootstrap task"
  value       = module.environment.db_bootstrap_security_group
}

output "db_bootstrap_log_group" {
  description = "Log group of the bootstrap task"
  value       = module.environment.db_bootstrap_log_group
}
