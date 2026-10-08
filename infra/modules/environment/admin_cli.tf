# -----------------------------------------------------------------------------
# One-off admin commands (`make user-role`): the backend image with the app's
# DATABASE_URL, started by aws ecs run-task in the backend's subnets and
# security group, because RDS is private. The command is overridden per run;
# the default only lists users. Uses the app's execution role (it reads the
# app secret) and no task role: the commands talk to the database only.
# -----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "admin_cli" {
  family                   = "${local.name}-admin-cli"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "admin-cli"
      image     = local.backend_image
      essential = true
      command   = ["python", "-m", "app.cli.user_role", "--list"]

      environment = [
        { name = "APP_ENV", value = var.environment },
        # The settings default to debug, which echoes every SQL statement
        { name = "APP_DEBUG", value = "false" },
      ]

      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_URL::"
        },
      ]

      logConfiguration = local.log_config["admin-cli"]
    },
  ])
}
