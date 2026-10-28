# Terraform creates the first task definition revision; CI registers new revisions per commit
# (see the ignore_changes blocks), so applying Terraform never rolls back an image.

# --- API (fastapi branch) --------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  volume {
    name = "storage"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.storage.id
      transit_encryption = "ENABLED"

      authorization_config {
        access_point_id = aws_efs_access_point.storage.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.app["api"].repository_url}:${var.api_image_tag}"
      essential = true

      portMappings = [{ containerPort = 5000, protocol = "tcp" }]

      environment = [
        { name = "STORAGE_DIR", value = "/app/storage" },
        { name = "CORS_ORIGINS", value = var.cors_origins },
      ]

      secrets = [
        { name = "RABBITMQ_URL", valueFrom = aws_secretsmanager_secret.rabbitmq_url.arn },
      ]

      mountPoints = [{ sourceVolume = "storage", containerPath = "/app/storage", readOnly = false }]

      healthCheck = {
        command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app["api"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  enable_execute_command            = true
  health_check_grace_period_seconds = 30

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 5000
  }

  service_registries {
    registry_arn = aws_service_discovery_service.app["api"].arn
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http, aws_efs_mount_target.storage]
}

# --- Worker (worker branch) ------------------------------------------------

locals {
  worker_langfuse_secrets = var.enable_langfuse ? [
    { name = "LANGFUSE_PUBLIC_KEY", valueFrom = "${aws_secretsmanager_secret.langfuse.arn}:public_key::" },
    { name = "LANGFUSE_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.langfuse.arn}:secret_key::" },
    { name = "LANGFUSE_HOST", valueFrom = "${aws_secretsmanager_secret.langfuse.arn}:host::" },
  ] : []
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = "${aws_ecr_repository.app["worker"].repository_url}:${var.worker_image_tag}"
      essential = true

      # Prometheus metrics endpoint.
      portMappings = [{ containerPort = 9100, protocol = "tcp" }]

      environment = [
        { name = "WORKER_PREFETCH", value = "1" },
      ]

      secrets = concat([
        { name = "RABBITMQ_URL", valueFrom = aws_secretsmanager_secret.rabbitmq_url.arn },
        { name = "GEMINI_API_KEY", valueFrom = aws_secretsmanager_secret.gemini_api_key.arn },
        { name = "GOOGLE_API_KEY", valueFrom = aws_secretsmanager_secret.gemini_api_key.arn },
      ], local.worker_langfuse_secrets)

      # The consumer touches ALIVE_FILE every 15s while connected to RabbitMQ.
      healthCheck = {
        command     = ["CMD", "python", "-c", "import os, time, sys; sys.exit(time.time() - os.path.getmtime(os.environ['ALIVE_FILE']) > 60)"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }

      # Fargate's maximum; gives an in-flight PDF time to finish and ack on scale-in.
      stopTimeout = 120

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app["worker"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "worker" {
  name            = "${local.name}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_min_count

  enable_execute_command = true

  capacity_provider_strategy {
    capacity_provider = var.worker_use_spot ? "FARGATE_SPOT" : "FARGATE"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.app["worker"].arn
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    # desired_count is owned by the autoscaler below.
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_ecs_cluster_capacity_providers.main]
}

resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  min_capacity       = var.worker_min_count
  max_capacity       = var.worker_max_count
}

resource "aws_appautoscaling_policy" "worker_cpu" {
  name               = "${local.name}-worker-cpu"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  resource_id        = aws_appautoscaling_target.worker.resource_id
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    target_value = var.worker_cpu_target

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    scale_out_cooldown = 60
    # Matches the KEDA cooldown so a follow-up burst doesn't pay the cold start again.
    scale_in_cooldown = 300
  }
}
