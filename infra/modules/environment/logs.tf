resource "aws_cloudwatch_log_group" "this" {
  for_each = toset(["backend", "frontend", "migration", "db-bootstrap"])

  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = var.log_retention_days
}
