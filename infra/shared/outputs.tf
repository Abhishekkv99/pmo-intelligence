output "vpc_id" {
  description = "PMO VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnets (ALBs, ECS tasks)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnets (RDS)"
  value       = aws_subnet.private[*].id
}

output "ecs_cluster_name" {
  description = "ECS cluster; GitHub variable ECS_CLUSTER_NAME"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "ecr_registry" {
  description = "ECR registry host; GitHub variable ECR_REGISTRY"
  value       = split("/", aws_ecr_repository.app["backend"].repository_url)[0]
}

output "ecr_repository_urls" {
  description = "Repository URL per image (backend, frontend)"
  value       = { for k, repo in aws_ecr_repository.app : k => repo.repository_url }
}

output "github_deploy_role_arn" {
  description = "Role the deploy job assumes; GitHub variable AWS_ROLE_ARN"
  value       = aws_iam_role.github_deploy.arn
}

output "deny_deletion_policy_arn" {
  description = "Policy denying deletion of PMO resources; attach to IAM users or groups"
  value       = aws_iam_policy.deny_deletion.arn
}

output "aws_region" {
  description = "Region; GitHub variable AWS_REGION"
  value       = var.aws_region
}

output "credential_expiry_topic_arn" {
  description = "SNS topic for credential expiry reminders"
  value       = aws_sns_topic.credential_expiry.arn
}

output "credential_expiry_reminders" {
  description = "Scheduled reminders (name => time in Europe/London)"
  value       = { for k, s in aws_scheduler_schedule.credential_expiry : k => s.schedule_expression }
}
