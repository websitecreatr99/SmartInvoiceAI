# One EC2 instance running the tracking branch's docker compose stack: Prometheus, Grafana,
# Loki + Alloy (receives FireLens logs on :3500), a CloudWatch exporter for Amazon MQ, and
# self-hosted Langfuse (:3002). It sits in a private subnet with no public IP; open the UIs with
# SSM port forwarding (see the monitoring_port_forward_commands output).
#
# The stack is copied from var.tracking_source_dir (a checkout of the tracking branch). A change
# to any file there changes the bundle hash in user_data, which replaces the instance.

locals {
  monitoring_count = var.enable_monitoring_host ? 1 : 0
  bundle_key       = "tracking/bundle.zip"
}

# --- Tracking bundle -------------------------------------------------------

data "archive_file" "tracking" {
  count = local.monitoring_count

  type        = "zip"
  source_dir  = var.tracking_source_dir
  output_path = "${path.module}/.build/tracking-bundle.zip"
  excludes    = [".git", ".git/**", ".env"]
}

# Small private bucket for deployment artifacts (only the tracking bundle today).
resource "aws_s3_bucket" "artifacts" {
  count  = local.monitoring_count
  bucket = "${local.name}-artifacts-${local.account_id}"
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  count  = local.monitoring_count
  bucket = aws_s3_bucket.artifacts[0].id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  count  = local.monitoring_count
  bucket = aws_s3_bucket.artifacts[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  count  = local.monitoring_count
  bucket = aws_s3_bucket.artifacts[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "tracking_bundle" {
  count = local.monitoring_count

  bucket      = aws_s3_bucket.artifacts[0].id
  key         = local.bundle_key
  source      = data.archive_file.tracking[0].output_path
  source_hash = data.archive_file.tracking[0].output_base64sha256

  depends_on = [aws_s3_bucket_server_side_encryption_configuration.artifacts]
}

# --- Generated credentials -------------------------------------------------
# No special characters: several of these are embedded in URLs (DATABASE_URL) and in .env.

resource "random_password" "monitoring" {
  for_each = var.enable_monitoring_host ? toset([
    "GRAFANA_ADMIN_PASSWORD",
    "LANGFUSE_ADMIN_PASSWORD",
    "LANGFUSE_DB_PASSWORD",
    "LANGFUSE_CLICKHOUSE_PASSWORD",
    "LANGFUSE_REDIS_PASSWORD",
    "LANGFUSE_MINIO_PASSWORD",
    "LANGFUSE_NEXTAUTH_SECRET",
    "LANGFUSE_SALT",
    "LANGFUSE_SECRET_KEY",
  ]) : toset([])

  length  = 32
  special = false
}

# Langfuse wants a 256-bit key as 64 hex characters.
resource "random_id" "langfuse_encryption_key" {
  count       = local.monitoring_count
  byte_length = 32
}

resource "random_id" "langfuse_public_key" {
  count       = local.monitoring_count
  byte_length = 16
}

locals {
  langfuse_public_key = var.enable_monitoring_host ? "pk-lf-${random_id.langfuse_public_key[0].hex}" : null
  langfuse_secret_key = var.enable_monitoring_host ? "sk-lf-${random_password.monitoring["LANGFUSE_SECRET_KEY"].result}" : null
}

# Keys are the .env names docker-compose.yml / docker-compose.aws.yml expect.
resource "aws_secretsmanager_secret" "monitoring" {
  count = local.monitoring_count

  name                    = "${local.name}/monitoring"
  description             = "Generated credentials for the monitoring host (Grafana, Langfuse)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "monitoring" {
  count = local.monitoring_count

  secret_id = aws_secretsmanager_secret.monitoring[0].id
  secret_string = jsonencode({
    GRAFANA_ADMIN_PASSWORD       = random_password.monitoring["GRAFANA_ADMIN_PASSWORD"].result
    LANGFUSE_ADMIN_PASSWORD      = random_password.monitoring["LANGFUSE_ADMIN_PASSWORD"].result
    LANGFUSE_DB_PASSWORD         = random_password.monitoring["LANGFUSE_DB_PASSWORD"].result
    LANGFUSE_CLICKHOUSE_PASSWORD = random_password.monitoring["LANGFUSE_CLICKHOUSE_PASSWORD"].result
    LANGFUSE_REDIS_PASSWORD      = random_password.monitoring["LANGFUSE_REDIS_PASSWORD"].result
    LANGFUSE_MINIO_PASSWORD      = random_password.monitoring["LANGFUSE_MINIO_PASSWORD"].result
    LANGFUSE_NEXTAUTH_SECRET     = random_password.monitoring["LANGFUSE_NEXTAUTH_SECRET"].result
    LANGFUSE_SALT                = random_password.monitoring["LANGFUSE_SALT"].result
    LANGFUSE_ENCRYPTION_KEY      = random_id.langfuse_encryption_key[0].hex
    LANGFUSE_PUBLIC_KEY          = local.langfuse_public_key
    LANGFUSE_SECRET_KEY          = local.langfuse_secret_key
  })
}

# --- IAM -------------------------------------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  count = local.monitoring_count

  name               = "${local.name}-monitoring-host"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# SSM Session Manager is the only way in (no SSH, no public IP).
resource "aws_iam_role_policy_attachment" "monitoring_ssm" {
  count = local.monitoring_count

  role       = aws_iam_role.monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "monitoring" {
  count = local.monitoring_count

  statement {
    sid       = "TrackingBundle"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts[0].arn}/${local.bundle_key}"]
  }

  statement {
    sid       = "MonitoringSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.monitoring[0].arn]
  }

  # CloudWatch exporter (Amazon MQ queue metrics). None of these support resource-level permissions.
  statement {
    sid = "CloudWatchExporter"
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
      "tag:GetResources",
      "mq:ListBrokers",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "monitoring" {
  count = local.monitoring_count

  name   = "monitoring-host"
  role   = aws_iam_role.monitoring[0].id
  policy = data.aws_iam_policy_document.monitoring[0].json
}

resource "aws_iam_instance_profile" "monitoring" {
  count = local.monitoring_count

  name = "${local.name}-monitoring-host"
  role = aws_iam_role.monitoring[0].name
}

# --- Instance --------------------------------------------------------------

data "aws_ssm_parameter" "al2023" {
  count = local.monitoring_count
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "monitoring" {
  count = local.monitoring_count

  # The AMI id is public, so use the unmasked value.
  ami                         = data.aws_ssm_parameter.al2023[0].insecure_value
  instance_type               = var.monitoring_instance_type
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.monitoring.id]
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.monitoring[0].name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
    # 2 hops so containers on the docker bridge (the YACE CloudWatch exporter) can reach IMDSv2.
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 50
    encrypted   = true
  }

  user_data = templatefile("${path.module}/monitoring_user_data.sh.tftpl", {
    region          = var.aws_region
    bundle_bucket   = aws_s3_bucket.artifacts[0].id
    bundle_key      = local.bundle_key
    bundle_hash     = data.archive_file.tracking[0].output_base64sha256
    secret_id       = aws_secretsmanager_secret.monitoring[0].arn
    broker_name     = aws_mq_broker.rabbitmq.broker_name
    compose_version = "v2.30.3" # >= 2.24.4 for `!override` in docker-compose.aws.yml
  })
  # A new bundle (hash above) or any other user_data change rebuilds the host.
  user_data_replace_on_change = true

  tags = { Name = "${local.name}-monitoring" }

  lifecycle {
    # A newer AMI published to the SSM parameter should not replace the host on its own.
    ignore_changes = [ami]
  }

  depends_on = [
    aws_s3_object.tracking_bundle,
    aws_secretsmanager_secret_version.monitoring,
    aws_iam_role_policy.monitoring,
    aws_iam_role_policy_attachment.monitoring_ssm,
  ]
}

# monitoring.invoiceai.local -> the instance's private IP (Langfuse for the worker, Loki push for
# FireLens).
resource "aws_service_discovery_service" "monitoring" {
  count = local.monitoring_count
  name  = "monitoring"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.main.id
    routing_policy = "MULTIVALUE"

    dns_records {
      type = "A"
      ttl  = 60
    }
  }
}

resource "aws_service_discovery_instance" "monitoring" {
  count = local.monitoring_count

  instance_id = aws_instance.monitoring[0].id
  service_id  = aws_service_discovery_service.monitoring[0].id

  attributes = {
    AWS_INSTANCE_IPV4 = aws_instance.monitoring[0].private_ip
  }
}
