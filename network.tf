data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs       = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  nat_count = var.single_nat_gateway ? 1 : var.az_count
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = local.name }
}

# Public subnets hold only the ALB and NAT gateways.
resource "aws_subnet" "public" {
  count             = var.az_count
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone = local.azs[count.index]

  tags = { Name = "${local.name}-public-${local.azs[count.index]}" }
}

# Private subnets hold ECS tasks, RabbitMQ and EFS.
resource "aws_subnet" "private" {
  count             = var.az_count
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = local.azs[count.index]

  tags = { Name = "${local.name}-private-${local.azs[count.index]}" }
}

resource "aws_eip" "nat" {
  count  = local.nat_count
  domain = "vpc"
  tags   = { Name = "${local.name}-nat-${count.index}" }
}

resource "aws_nat_gateway" "main" {
  count         = local.nat_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = { Name = "${local.name}-nat-${count.index}" }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name}-public" }
}

resource "aws_route_table_association" "public" {
  count          = var.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  count  = var.az_count
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[var.single_nat_gateway ? 0 : count.index].id
  }

  tags = { Name = "${local.name}-private-${local.azs[count.index]}" }
}

resource "aws_route_table_association" "private" {
  count          = var.az_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# Upload traffic (API -> S3 -> worker) and the tracking bundle stay off the NAT gateway.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id

  tags = { Name = "${local.name}-s3" }
}

# --- Security groups -------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Public HTTP/HTTPS into the load balancer"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "frontend" {
  name        = "${local.name}-frontend"
  description = "Next.js frontend tasks"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "api" {
  name        = "${local.name}-api"
  description = "FastAPI tasks"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "worker" {
  name        = "${local.name}-worker"
  description = "Worker tasks"
  vpc_id      = aws_vpc.main.id
}

# Monitoring host (monitoring_host.tf): Prometheus, Grafana, Loki/Alloy, Langfuse.
resource "aws_security_group" "monitoring" {
  name        = "${local.name}-monitoring"
  description = "Monitoring stack (Prometheus, Grafana, Langfuse)"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "mq" {
  name        = "${local.name}-rabbitmq"
  description = "Amazon MQ RabbitMQ broker"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "efs" {
  name        = "${local.name}-efs"
  description = "EFS job storage for the API"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_ingress_rule" "frontend_from_alb" {
  security_group_id            = aws_security_group.frontend.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 3000
}

# The frontend's Next.js server proxies /api/* to api.invoiceai.local:5000.
resource "aws_vpc_security_group_ingress_rule" "api_from_frontend" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.frontend.id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
}

# Prometheus scrapes the API's /metrics on the app port.
resource "aws_vpc_security_group_ingress_rule" "api_from_monitoring" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
}

resource "aws_vpc_security_group_ingress_rule" "worker_metrics_from_monitoring" {
  security_group_id            = aws_security_group.worker.id
  referenced_security_group_id = aws_security_group.monitoring.id
  ip_protocol                  = "tcp"
  from_port                    = 9100
  to_port                      = 9100
}

resource "aws_vpc_security_group_ingress_rule" "mq_from_api" {
  security_group_id            = aws_security_group.mq.id
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 5671
  to_port                      = 5671
}

resource "aws_vpc_security_group_ingress_rule" "mq_from_worker" {
  security_group_id            = aws_security_group.mq.id
  referenced_security_group_id = aws_security_group.worker.id
  ip_protocol                  = "tcp"
  from_port                    = 5671
  to_port                      = 5671
}

resource "aws_vpc_security_group_ingress_rule" "efs_from_api" {
  security_group_id            = aws_security_group.efs.id
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 2049
  to_port                      = 2049
}

# Worker -> self-hosted Langfuse on the monitoring host.
resource "aws_vpc_security_group_ingress_rule" "monitoring_langfuse_from_worker" {
  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = aws_security_group.worker.id
  ip_protocol                  = "tcp"
  from_port                    = 3002
  to_port                      = 3002
}

# FireLens (Fluent Bit) in every task -> Alloy's Loki push endpoint on the monitoring host.
resource "aws_vpc_security_group_ingress_rule" "monitoring_loki_push" {
  for_each = {
    api      = aws_security_group.api.id
    worker   = aws_security_group.worker.id
    frontend = aws_security_group.frontend.id
  }

  security_group_id            = aws_security_group.monitoring.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 3500
  to_port                      = 3500
}

# Outbound: tasks need ECR, Secrets Manager, CloudWatch, S3, Gemini and the monitoring host.
resource "aws_vpc_security_group_egress_rule" "all" {
  for_each = {
    alb        = aws_security_group.alb.id
    frontend   = aws_security_group.frontend.id
    api        = aws_security_group.api.id
    worker     = aws_security_group.worker.id
    monitoring = aws_security_group.monitoring.id
  }

  security_group_id = each.value
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
