output "url" {
  description = "Public URL"
  value       = local.url
}

output "hosted_zone_name_servers" {
  description = "Name servers for the NS record that delegates the hostname from itcapp.ai"
  value       = aws_route53_zone.this.name_servers
}

output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.this.dns_name
}

output "backend_service_name" {
  description = "Backend ECS service"
  value       = aws_ecs_service.backend.name
}

output "frontend_service_name" {
  description = "Frontend ECS service"
  value       = aws_ecs_service.frontend.name
}

output "app_secret_arn" {
  description = "App secret (JSON of the keys in local.app_secret_keys)"
  value       = aws_secretsmanager_secret.app.arn
}

output "db_endpoint" {
  description = "RDS endpoint (host:port)"
  value       = aws_db_instance.this.endpoint
}

output "db_master_secret_arn" {
  description = "RDS-managed secret with the master credentials"
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}

output "media_bucket" {
  description = "Media bucket"
  value       = aws_s3_bucket.media.id
}

output "backend_security_group_id" {
  description = "Backend task security group (one-off tasks that need the database use it)"
  value       = aws_security_group.backend.id
}

output "ecs_execution_role_arn" {
  description = "Task execution role"
  value       = aws_iam_role.execution.arn
}

output "ecs_task_role_arn" {
  description = "Backend task role"
  value       = aws_iam_role.task.arn
}

output "ses_identity" {
  description = "SES sending domain"
  value       = aws_sesv2_email_identity.this.email_identity
}
