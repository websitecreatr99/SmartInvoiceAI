output "app_url" {
  description = "Public URL of the app (ALB -> frontend; the frontend proxies /api/* to the API)."
  value       = "${local.https_enabled ? "https" : "http"}://${aws_lb.main.dns_name}"
}

output "alb_dns_name" {
  description = "Point your DNS record (CNAME/alias) here when using a custom domain."
  value       = aws_lb.main.dns_name
}

output "ecr_repository_urls" {
  description = "ECR repositories for the api (fastapi branch), worker (worker branch) and frontend (frontend branch) images."
  value       = { for k, r in aws_ecr_repository.app : k => r.repository_url }
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_names" {
  value = {
    api      = aws_ecs_service.api.name
    worker   = aws_ecs_service.worker.name
    frontend = aws_ecs_service.frontend.name
  }
}

output "ecs_task_definition_families" {
  value = {
    api      = aws_ecs_task_definition.api.family
    worker   = aws_ecs_task_definition.worker.family
    frontend = aws_ecs_task_definition.frontend.family
  }
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository variable; used by the fastapi, worker and frontend workflows."
  value       = aws_iam_role.github_deploy.arn
}

output "uploads_bucket" {
  description = "S3 bucket for uploaded files (STORAGE_BUCKET on the API and worker)."
  value       = aws_s3_bucket.uploads.bucket
}

output "secret_arns" {
  description = "Secrets Manager secrets. gemini_api_key must hold a value before the worker starts."
  value = {
    rabbitmq_url   = aws_secretsmanager_secret.rabbitmq_url.arn
    gemini_api_key = aws_secretsmanager_secret.gemini_api_key.arn
    langfuse       = aws_secretsmanager_secret.langfuse.arn
    monitoring     = var.enable_monitoring_host ? aws_secretsmanager_secret.monitoring[0].arn : null
  }
}

output "rabbitmq_console_url" {
  description = "Amazon MQ management console (reachable from inside the VPC only)."
  value       = aws_mq_broker.rabbitmq.instances[0].console_url
}

# --- Monitoring host -------------------------------------------------------

output "monitoring_instance_id" {
  description = "EC2 instance running the tracking stack (Grafana, Prometheus, Loki, Langfuse)."
  value       = var.enable_monitoring_host ? aws_instance.monitoring[0].id : null
}

output "monitoring_port_forward_commands" {
  description = "Run one, then open http://localhost:<port>. Needs the Session Manager plugin for the AWS CLI."
  value = var.enable_monitoring_host ? {
    for ui, port in { grafana = 3001, langfuse = 3002, prometheus = 9090 } : ui => join(" ", [
      "aws ssm start-session --region ${var.aws_region}",
      "--target ${aws_instance.monitoring[0].id}",
      "--document-name AWS-StartPortForwardingSession",
      "--parameters portNumber=${port},localPortNumber=${port}",
    ])
  } : null
}

# --- Network ---------------------------------------------------------------

output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "monitoring_security_group_id" {
  description = "Security group of the monitoring host; allowed to scrape api:5000 and worker:9100."
  value       = aws_security_group.monitoring.id
}

output "service_discovery_namespace" {
  description = "Private DNS namespace: api.<ns>:5000, worker.<ns>:9100, frontend.<ns>:3000, monitoring.<ns>."
  value       = aws_service_discovery_private_dns_namespace.main.name
}

output "prometheus_remote_write_url" {
  value = var.enable_managed_prometheus ? "${aws_prometheus_workspace.main[0].prometheus_endpoint}api/v1/remote_write" : null
}
