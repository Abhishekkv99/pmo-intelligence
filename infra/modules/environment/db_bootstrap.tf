# -----------------------------------------------------------------------------
# Database bootstrap: a one-off task (backend image, app.cli.db_bootstrap)
# that creates the pmo_app login, gives it the database, enables pgvector and
# writes DATABASE_URL into the app secret. Run with `make db-bootstrap`.
# Its roles are the only ones that may read the RDS master secret or write the
# app secret; the app's own roles cannot.
# -----------------------------------------------------------------------------

resource "aws_iam_role" "db_bootstrap_execution" {
  name               = "${local.name}-db-bootstrap-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
}

resource "aws_iam_role_policy_attachment" "db_bootstrap_execution" {
  role       = aws_iam_role.db_bootstrap_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Injects the master password into the container at start
data "aws_iam_policy_document" "db_bootstrap_execution" {
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_db_instance.this.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "db_bootstrap_execution" {
  name   = "${local.name}-db-bootstrap-master-secret"
  role   = aws_iam_role.db_bootstrap_execution.id
  policy = data.aws_iam_policy_document.db_bootstrap_execution.json
}

resource "aws_iam_role" "db_bootstrap_task" {
  name               = "${local.name}-db-bootstrap-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_trust.json
}

# The script itself reads and rewrites the app secret's DATABASE_URL
data "aws_iam_policy_document" "db_bootstrap_task" {
  statement {
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"]
    resources = [aws_secretsmanager_secret.app.arn]
  }
}

resource "aws_iam_role_policy" "db_bootstrap_task" {
  name   = "${local.name}-db-bootstrap-app-secret"
  role   = aws_iam_role.db_bootstrap_task.id
  policy = data.aws_iam_policy_document.db_bootstrap_task.json
}

resource "aws_ecs_task_definition" "db_bootstrap" {
  family                   = "${local.name}-db-bootstrap"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.db_bootstrap_execution.arn
  task_role_arn            = aws_iam_role.db_bootstrap_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "db-bootstrap"
      image     = local.backend_image
      essential = true
      command   = ["python", "-m", "app.cli.db_bootstrap"]

      environment = [
        { name = "DB_HOST", value = aws_db_instance.this.address },
        { name = "DB_PORT", value = tostring(aws_db_instance.this.port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_MASTER_USERNAME", value = var.db_master_username },
        { name = "APP_DB_USER", value = "pmo_app" },
        { name = "APP_SECRET_ARN", value = aws_secretsmanager_secret.app.arn },
        { name = "AWS_REGION", value = var.aws_region },
      ]

      secrets = [
        {
          name      = "DB_MASTER_PASSWORD"
          valueFrom = "${aws_db_instance.this.master_user_secret[0].secret_arn}:password::"
        },
      ]

      logConfiguration = local.log_config["db-bootstrap"]
    },
  ])
}
