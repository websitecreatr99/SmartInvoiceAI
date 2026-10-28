# Managed RabbitMQ replaces the rabbitmq container from docker-compose / k8s.
resource "random_password" "mq" {
  length  = 32
  special = false # Amazon MQ rejects , : = in passwords
}

resource "aws_mq_broker" "rabbitmq" {
  broker_name        = local.name
  engine_type        = "RabbitMQ"
  engine_version     = "3.13"
  host_instance_type = var.mq_instance_type
  deployment_mode    = var.mq_deployment_mode

  publicly_accessible        = false
  auto_minor_version_upgrade = true
  security_groups            = [aws_security_group.mq.id]
  subnet_ids = (
    var.mq_deployment_mode == "SINGLE_INSTANCE"
    ? [aws_subnet.private[0].id]
    : aws_subnet.private[*].id
  )

  user {
    username = var.mq_username
    password = random_password.mq.result
  }

  logs {
    general = true
  }

  maintenance_window_start_time {
    day_of_week = "SUNDAY"
    time_of_day = "20:30"
    time_zone   = "UTC"
  }
}

locals {
  # Endpoint looks like amqps://b-xxxx.mq.<region>.amazonaws.com:5671; add credentials and the default vhost.
  mq_endpoint = aws_mq_broker.rabbitmq.instances[0].endpoints[0]
  rabbitmq_url = format(
    "amqps://%s:%s@%s/%%2F",
    var.mq_username,
    random_password.mq.result,
    trimprefix(local.mq_endpoint, "amqps://"),
  )
}
