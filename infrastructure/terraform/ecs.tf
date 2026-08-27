# ECS Fargate (Step 8) — cluster, task definitions (api, web, and a
# one-off migration task), and the two services.
#
# Migration strategy (Step 14): the API image's entrypoint runs
# `alembic upgrade head` on startup ONLY when RUN_MIGRATIONS_ON_STARTUP
# is true (the local-development default). In ECS it is set to "false"
# on the api service so a rolling deploy of N tasks never races N
# concurrent migrations; instead, migrations run as an explicit one-off
# task (aws ecs run-task with the `migrate` task definition, whose
# container command overrides the entrypoint args to
# `alembic upgrade head`) BEFORE the service is updated — see
# docs/aws-deployment.md §"Deploy flow" for the exact sequence and
# .github/workflows/deploy.yml for the automation.

resource "aws_ecs_cluster" "main" {
  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "disabled" # cost choice — CloudWatch basic metrics + logs suffice at this scale
  }
}

# --- log groups (Step 15) ---------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "web" {
  name              = "/ecs/${var.project}-web"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "migrate" {
  name              = "/ecs/${var.project}-migrate"
  retention_in_days = var.log_retention_days
}

# --- shared container configuration ----------------------------------------

locals {
  api_image = "${aws_ecr_repository.repos["${var.project}-api"].repository_url}:${var.api_image_tag}"
  web_image = "${aws_ecr_repository.repos["${var.project}-web"].repository_url}:${var.web_image_tag}"

  # The application's real configuration surface (app/core/config.py) —
  # names preserved exactly; nothing renamed for AWS (Step 13). Secrets
  # (POSTGRES_PASSWORD, AI_PROVIDER_API_KEY) are injected via
  # `secrets`/valueFrom below, never as plain environment values.
  api_environment = [
    { name = "APP_ENV", value = var.environment == "prod" ? "production" : var.environment },
    { name = "LOG_LEVEL", value = var.log_level },
    { name = "CORS_ORIGINS", value = local.site_origin },
    { name = "POSTGRES_HOST", value = aws_db_instance.main.address },
    { name = "POSTGRES_PORT", value = "5432" },
    { name = "POSTGRES_DB", value = var.db_name },
    { name = "POSTGRES_USER", value = var.db_username },
    { name = "REDIS_HOST", value = aws_elasticache_replication_group.main.primary_endpoint_address },
    { name = "REDIS_PORT", value = "6379" },
    { name = "AI_PROVIDER", value = var.ai_provider },
    { name = "AI_MODEL", value = var.ai_model },
    { name = "RUN_MIGRATIONS_ON_STARTUP", value = "false" },
  ]

  api_secrets = [
    { name = "POSTGRES_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn },
    { name = "AI_PROVIDER_API_KEY", valueFrom = aws_secretsmanager_secret.ai_api_key.arn },
  ]
}

# --- task definitions -------------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = local.api_image
      essential = true

      portMappings = [{ containerPort = local.api_port, protocol = "tcp" }]

      environment = local.api_environment
      secrets     = local.api_secrets

      # Container-level LIVENESS (restart decision) — /health/live, per
      # the existing Dockerfile HEALTHCHECK (which Fargate ignores, so
      # it is restated here). Readiness (traffic decision) is the ALB's
      # /health/ready check in alb.tf.
      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health/live', timeout=2).status == 200 else sys.exit(1)\"",
        ]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
}

# Same image as the api task; its container command becomes the
# entrypoint's arguments, and the entrypoint execs any arguments it
# receives — so this task runs exactly `alembic upgrade head` and exits.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name_prefix}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([
    {
      name      = "migrate"
      image     = local.api_image
      essential = true
      command   = ["alembic", "upgrade", "head"]

      environment = local.api_environment
      secrets     = local.api_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.migrate.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "migrate"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name_prefix}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.web_cpu
  memory                   = var.web_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([
    {
      name      = "web"
      image     = local.web_image
      essential = true

      portMappings = [{ containerPort = local.web_port, protocol = "tcp" }]

      environment = [
        # Same fix docker-compose.yml carries: Next standalone binds to
        # $HOSTNAME, which the container runtime sets to the task ID —
        # 0.0.0.0 makes it listen on every interface including loopback
        # (required for the container health check below).
        { name = "HOSTNAME", value = "0.0.0.0" },
        { name = "PORT", value = tostring(local.web_port) },
      ]

      healthCheck = {
        command = [
          "CMD-SHELL",
          "node -e \"fetch('http://localhost:3000/dashboard').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\"",
        ]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.web.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "web"
        }
      }
    }
  ])
}

# --- services ---------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private_app[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = local.api_port
  }

  health_check_grace_period_seconds = 60

  # CI deploys register new task-definition revisions outside Terraform
  # (immutable git-SHA image tags); Terraform must not roll the service
  # back to the revision it last knew about on unrelated applies.
  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http, aws_lb_listener_rule.api]
}

resource "aws_ecs_service" "web" {
  name            = "web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private_app[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = local.web_port
  }

  health_check_grace_period_seconds = 60

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}
