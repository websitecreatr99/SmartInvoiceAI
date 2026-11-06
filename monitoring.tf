# Private DNS (Cloud Map) for the ECS services. Each service registers one A record per task:
#   api.<namespace>:5000       the frontend's /api proxy target, and Prometheus /metrics
#   worker.<namespace>:9100    Prometheus /metrics (dns_sd_configs, type A)
#   frontend.<namespace>:3000
# monitoring.<namespace> (the monitoring host) is registered in monitoring_host.tf.

resource "aws_service_discovery_private_dns_namespace" "main" {
  name        = "${var.project}.local"
  description = "Private DNS for ${local.name} services"
  vpc         = aws_vpc.main.id
}

resource "aws_service_discovery_service" "app" {
  for_each = local.images
  name     = each.key

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.main.id
    routing_policy = "MULTIVALUE"

    dns_records {
      type = "A"
      ttl  = 10
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# Optional managed metrics store; Prometheus from the monitoring repo can remote_write into it
# and Grafana can query it with SigV4.
resource "aws_prometheus_workspace" "main" {
  count = var.enable_managed_prometheus ? 1 : 0
  alias = local.name
}
