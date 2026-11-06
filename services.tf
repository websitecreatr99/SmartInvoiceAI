# Terraform creates the first task definition revision; CI registers new revisions per commit
# (see the ignore_changes blocks), so applying Terraform never rolls back an image.

# --- Logging ---------------------------------------------------------------
# With the monitoring host, each task gets a FireLens (Fluent Bit) sidecar that ships the app
# container's stdout to Alloy's Loki push endpoint on monitoring.invoiceai.local:3500.
# Without it, the app containers log straight to CloudWatch (awslogs) as before.

locals {
  ecs_services   = ["api", "worker", "frontend"]
  monitoring_dns = "monitoring.${aws_service_discovery_private_dns_namespace.main.name}"

  log_router = {
    for svc in local.ecs_services : svc => {
      name              = "log_router"
      image             = "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable"
      essential         = false
      memoryReservation = 50

      firelensConfiguration = {
        type    = "fluentbit"
        options = { "enable-ecs-log-metadata" = "false" }
      }

      # Fluent Bit's own logs still go to CloudWatch, so a broken pipeline is debuggable.
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app[svc].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "log_router"
        }
      }
    }
  }

  # Containers to put in front of each task's app container: the sidecar, or nothing.
  log_router_containers = {
    for svc in local.ecs_services : svc => [for c in [local.log_router[svc]] : c if var.enable_monitoring_host]
  }

  # Both branches are {logDriver = string, options = map(string)} so the conditional type-checks.
  app_log_configuration = {
    for svc in local.ecs_services : svc => (
      var.enable_monitoring_host
      ? {
        logDriver = "awsfirelens"
        options = tomap({
          Name            = "loki"
          host            = local.monitoring_dns
          port            = "3500"
          uri             = "/loki/api/v1/push"
          labels          = "service=${svc}"
          remove_keys     = "container_id,container_name,source"
          line_format     = "key_value"
          drop_single_key = "on"
        })
      }
      : {
        logDriver = "awslogs"
        options = tomap({
          awslogs-group         = aws_cloudwatch_log_group.app[svc].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = svc
        })
      }
    )
  }

  # The app container waits for Fluent Bit to start so no early log lines are lost.
  app_depends_on = var.enable_monitoring_host ? [{ containerName = "log_router", condition = "START" }] : null
}

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

  container_definitions = jsonencode(concat(local.log_router_containers["api"], [
    {
      name      = "api"
      image     = "${aws_ecr_repository.app["api"].repository_url}:${var.api_image_tag}"
      essential = true

      portMappings = [{ containerPort = 5000, protocol = "tcp" }]

      environment = [
        { name = "STORAGE_DIR", value = "/app/storage" },
        { name = "CORS_ORIGINS", value = var.cors_origins },
        { name = "STORAGE_BUCKET", value = aws_s3_bucket.uploads.bucket },
        { name = "AWS_REGION", value = var.aws_region },
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

      dependsOn        = local.app_depends_on
      logConfiguration = local.app_log_configuration["api"]
    }
  ]))
}

# Not behind the ALB: only the frontend (and Prometheus) reach it, at api.invoiceai.local:5000.
resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
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

  depends_on = [aws_efs_mount_target.storage, aws_secretsmanager_secret_version.rabbitmq_url]
}

# --- Worker (worker branch) ------------------------------------------------

locals {
  # The monitoring host runs Langfuse and fills the langfuse secret itself (monitoring_host.tf).
  langfuse_enabled = var.enable_langfuse || var.enable_monitoring_host

  worker_langfuse_secrets = local.langfuse_enabled ? [
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

  container_definitions = jsonencode(concat(local.log_router_containers["worker"], [
    {
      name      = "worker"
      image     = "${aws_ecr_repository.app["worker"].repository_url}:${var.worker_image_tag}"
      essential = true

      # Prometheus metrics endpoint.
      portMappings = [{ containerPort = 9100, protocol = "tcp" }]

      environment = [
        { name = "WORKER_PREFETCH", value = "1" },
        { name = "GEMINI_MODEL", value = var.gemini_model },
        { name = "OCR_DPI", value = tostring(var.ocr_dpi) },
        { name = "STORAGE_BUCKET", value = aws_s3_bucket.uploads.bucket },
        { name = "AWS_REGION", value = var.aws_region },
      ]

      secrets = concat([
        { name = "RABBITMQ_URL", valueFrom = aws_secretsmanager_secret.rabbitmq_url.arn },
        { name = "GEMINI_API_KEY", valueFrom = aws_secretsmanager_secret.gemini_api_key.arn },
        { name = "GOOGLE_API_KEY", valueFrom = aws_secretsmanager_secret.gemini_api_key.arn },
      ], local.worker_langfuse_secrets)

      # The consumer touches ALIVE_FILE every 15s while connected to RabbitMQ. PaddleOCR model
      # loading on first start can take minutes, hence the long start period.
      healthCheck = {
        command     = ["CMD", "python", "-c", "import os, time, sys; sys.exit(time.time() - os.path.getmtime(os.environ['ALIVE_FILE']) > 60)"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 300
      }

      # Fargate's maximum; gives an in-flight PDF time to finish and ack on deploys.
      stopTimeout = 120

      dependsOn        = local.app_depends_on
      logConfiguration = local.app_log_configuration["worker"]
    }
  ]))
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

  # Secrets must hold a value before the first task starts, or ECS fails to inject them.
  depends_on = [
    aws_ecs_cluster_capacity_providers.main,
    aws_secretsmanager_secret_version.rabbitmq_url,
    aws_secretsmanager_secret_version.gemini_api_key,
    aws_secretsmanager_secret_version.langfuse,
  ]
}

# --- Worker autoscaling on queue depth ---------------------------------------
# Amazon MQ publishes per-queue metrics for RabbitMQ to CloudWatch every minute:
#   MessageReadyCount = jobs waiting for a worker, MessageCount = ready + unacked (in progress).
# Scale out as soon as jobs are waiting; scale back to the minimum only after the queue has been
# completely empty for 10 minutes.
#
# The worker also sets ECS task scale-in protection (ecs:UpdateTaskProtection, see ecs.tf) while
# it processes a job, so a scale-in never kills a busy task: ECS only stops unprotected ones.

locals {
  worker_queue_dimensions = {
    Broker      = aws_mq_broker.rabbitmq.broker_name
    VirtualHost = "/"
    Queue       = "invoice.jobs"
  }
}

resource "aws_appautoscaling_target" "worker" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  min_capacity       = var.worker_min_count
  max_capacity       = var.worker_max_count
}

resource "aws_appautoscaling_policy" "worker_scale_out" {
  name               = "${local.name}-worker-queue-scale-out"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  resource_id        = aws_appautoscaling_target.worker.resource_id
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    metric_aggregation_type = "Maximum"
    # New tasks need a few minutes to pull the image and load models; while the cooldown runs,
    # a repeated alarm only adds capacity beyond what the previous step already asked for.
    cooldown = 180

    # Bounds are relative to the alarm threshold (0 ready messages).
    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = 5
      scaling_adjustment          = 1
    }

    step_adjustment {
      metric_interval_lower_bound = 5
      metric_interval_upper_bound = 20
      scaling_adjustment          = 3
    }

    step_adjustment {
      metric_interval_lower_bound = 20
      scaling_adjustment          = 5
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_queue_backlog" {
  alarm_name          = "${local.name}-worker-queue-backlog"
  alarm_description   = "Jobs are waiting in invoice.jobs: add workers."
  namespace           = "AWS/AmazonMQ"
  metric_name         = "MessageReadyCount"
  dimensions          = local.worker_queue_dimensions
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.worker_scale_out.arn]
}

resource "aws_appautoscaling_policy" "worker_scale_in" {
  name               = "${local.name}-worker-queue-scale-in"
  service_namespace  = aws_appautoscaling_target.worker.service_namespace
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  resource_id        = aws_appautoscaling_target.worker.resource_id
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    metric_aggregation_type = "Maximum"
    cooldown                = 300

    # MessageCount <= 0: back to the minimum.
    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = var.worker_min_count
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_queue_idle" {
  alarm_name          = "${local.name}-worker-queue-idle"
  alarm_description   = "invoice.jobs has had no ready or in-flight jobs for 10 minutes: scale workers to the minimum."
  namespace           = "AWS/AmazonMQ"
  metric_name         = "MessageCount"
  dimensions          = local.worker_queue_dimensions
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 10
  datapoints_to_alarm = 10
  threshold           = 0
  comparison_operator = "LessThanOrEqualToThreshold"
  # No data is not proof of an empty queue; never scale in on missing metrics.
  treat_missing_data = "notBreaching"
  alarm_actions      = [aws_appautoscaling_policy.worker_scale_in.arn]
}

# --- Frontend (frontend branch) --------------------------------------------

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.frontend_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  # The /api/* proxy target (http://api.invoiceai.local:5000) is baked into the image at build
  # time, so nothing about the API is configured here.
  container_definitions = jsonencode(concat(local.log_router_containers["frontend"], [
    {
      name      = "frontend"
      image     = "${aws_ecr_repository.app["frontend"].repository_url}:${var.frontend_image_tag}"
      essential = true

      portMappings = [{ containerPort = 3000, protocol = "tcp" }]

      environment = [
        { name = "PORT", value = "3000" },
        { name = "HOSTNAME", value = "0.0.0.0" },
        { name = "NODE_ENV", value = "production" },
      ]

      dependsOn        = local.app_depends_on
      logConfiguration = local.app_log_configuration["frontend"]
    }
  ]))
}

resource "aws_ecs_service" "frontend" {
  name            = "${local.name}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  enable_execute_command            = true
  health_check_grace_period_seconds = 30

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.frontend.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  service_registries {
    registry_arn = aws_service_discovery_service.app["frontend"].arn
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  # The target group must be attached to a listener before a service can register into it.
  depends_on = [aws_lb_listener.http]
}
