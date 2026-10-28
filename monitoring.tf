# Hooks for the monitoring repository. Prometheus, Grafana and Langfuse are deployed from there
# as their own ECS services in this cluster/VPC, using the outputs of this stack.
#
# Prometheus scrape targets (dns_sd_configs, type A):
#   api.<namespace>:5000      /metrics
#   worker.<namespace>:9100   /metrics

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
