# -----------------------------------------------------------------------------
# ECS: backend (migration init container + app) and frontend, behind the ALB.
# CI pushes a new image under var.image_tag and forces a new deployment; the
# task definitions themselves change only through Terraform.
# -----------------------------------------------------------------------------

locals {
  backend_image  = "${var.ecr_repository_urls["backend"]}:${var.image_tag}"
  frontend_image = "${var.ecr_repository_urls["frontend"]}:${var.image_tag}"

  log_config = {
    for k, group in aws_cloudwatch_log_group.this : k => {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = group.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
        "mode"                  = "non-blocking"
        "max-buffer-size"       = "25m"
      }
    }
  }

  backend_environment = [
    { name = "APP_ENV", value = var.environment },
    { name = "APP_DEBUG", value = "false" },
    { name = "APP_PORT", value = "8000" },
    { name = "FRONTEND_URL", value = local.url },
    { name = "BACKEND_URL", value = local.url },
    { name = "STORAGE_BACKEND", value = "s3" },
    { name = "S3_BUCKET_NAME", value = aws_s3_bucket.media.id },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "COOKIE_SECURE", value = "true" },
    # Microsoft Entra ID is the only sign-in here; with this false,
    # /auth/register and /auth/login answer 403. CI keeps it true.
    { name = "LOCAL_AUTH_ENABLED", value = "false" },
    { name = "AZURE_REDIRECT_URI", value = "${local.url}/auth/callback/microsoft" },
    { name = "AZURE_OPENAI_API_VERSION", value = var.azure_openai_api_version },
    { name = "BOOTSTRAP_ADMIN_EMAILS", value = var.bootstrap_admin_emails },
    { name = "PROCESSING_CONCURRENCY", value = tostring(var.processing_concurrency) },
    { name = "RECORDINGS_SOURCE_BUCKET", value = var.recordings_source_bucket },
    { name = "RECORDINGS_SOURCE_PREFIX", value = var.recordings_source_prefix },
    { name = "RECORDINGS_SCAN_ENABLED", value = tostring(var.recordings_scan_enabled) },
    { name = "HEALTH_DAILY_ENABLED", value = tostring(var.health_daily_enabled) },
    # Teams chat; the certificate and the client state are in the secret
    { name = "TEAMS_ENABLED", value = tostring(var.teams_enabled) },
    { name = "TEAMS_DISCOVERY_ENABLED", value = tostring(var.teams_discovery_enabled) },
    { name = "GRAPH_TENANT_ID", value = var.graph_tenant_id },
    { name = "GRAPH_CLIENT_ID", value = var.graph_client_id },
    { name = "TEAMS_DISCOVERY_ACCOUNTS", value = jsonencode(var.teams_discovery_accounts) },
    { name = "TEAMS_NOTIFICATION_BASE_URL", value = local.url },
  ]

  backend_secrets = [
    for key in local.app_secret_keys : {
      name      = key
      valueFrom = "${aws_secretsmanager_secret.app.arn}:${key}::"
    }
  ]
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    # Runs the migrations, then exits; the app starts only if it succeeded
    {
      name      = "migration"
      image     = local.backend_image
      essential = false
      command   = ["alembic", "upgrade", "head"]

      environment = [
        { name = "APP_ENV", value = var.environment },
      ]

      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_URL::"
        },
      ]

      logConfiguration = local.log_config["migration"]
    },
    {
      name      = "backend"
      image     = local.backend_image
      essential = true

      portMappings = [
        { containerPort = 8000, protocol = "tcp" },
      ]

      environment = local.backend_environment
      secrets     = local.backend_secrets

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }

      dependsOn = [
        { containerName = "migration", condition = "SUCCESS" },
      ]

      logConfiguration = local.log_config["backend"]
    },
  ])
}

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = aws_iam_role.execution.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "frontend"
      image     = local.frontend_image
      essential = true

      portMappings = [
        { containerPort = 3000, protocol = "tcp" },
      ]

      environment = [
        { name = "PORT", value = "3000" },
        { name = "HOSTNAME", value = "0.0.0.0" },
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "node -e \"require('http').get('http://localhost:3000/api/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = local.log_config["frontend"]
    },
  ])
}

resource "aws_ecs_service" "backend" {
  name            = "${local.name}-backend"
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  health_check_grace_period_seconds  = 120
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.https]
}

resource "aws_ecs_service" "frontend" {
  name            = "${local.name}-frontend"
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.frontend.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  depends_on = [aws_lb_listener.https]
}
