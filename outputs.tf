output "api_url" {
  description = "Public URL of the API load balancer."
  value       = "${local.https_enabled ? "https" : "http"}://${aws_lb.api.dns_name}"
}

output "ecr_repository_urls" {
  description = "ECR repositories for the api (fastapi branch) and worker (worker branch) images."
  value       = { for k, r in aws_ecr_repository.app : k => r.repository_url }
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_names" {
  value = { api = aws_ecs_service.api.name, worker = aws_ecs_service.worker.name }
}

output "ecs_task_definition_families" {
  value = { api = aws_ecs_task_definition.api.family, worker = aws_ecs_task_definition.worker.family }
}

output "github_deploy_role_arn" {
  description = "Role for aws-actions/configure-aws-credentials in both branch workflows."
  value       = aws_iam_role.github_deploy.arn
}

output "secret_arns" {
  description = "Secrets to populate out of band (gemini, langfuse)."
  value = {
    rabbitmq_url   = aws_secretsmanager_secret.rabbitmq_url.arn
    gemini_api_key = aws_secretsmanager_secret.gemini_api_key.arn
    langfuse       = aws_secretsmanager_secret.langfuse.arn
  }
}

output "rabbitmq_console_url" {
  description = "Amazon MQ management console (reachable from inside the VPC only)."
  value       = aws_mq_broker.rabbitmq.instances[0].console_url
}

# --- Inputs for the monitoring repository ----------------------------------

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
  description = "Attach to the Prometheus/Grafana/Langfuse tasks so they can scrape the API and worker."
  value       = aws_security_group.monitoring.id
}

output "service_discovery_namespace" {
  description = "Private DNS namespace; scrape api.<ns>:5000 and worker.<ns>:9100."
  value       = aws_service_discovery_private_dns_namespace.main.name
}

output "prometheus_remote_write_url" {
  value = var.enable_managed_prometheus ? "${aws_prometheus_workspace.main[0].prometheus_endpoint}api/v1/remote_write" : null
}
