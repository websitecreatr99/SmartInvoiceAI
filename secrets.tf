# Terraform owns the RabbitMQ URL because it generates the password.
resource "aws_secretsmanager_secret" "rabbitmq_url" {
  name                    = "${local.name}/rabbitmq-url"
  description             = "AMQPS connection string for the API and worker"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "rabbitmq_url" {
  secret_id     = aws_secretsmanager_secret.rabbitmq_url.id
  secret_string = local.rabbitmq_url
}

# The worker needs this before its first task starts. Either pass var.gemini_api_key (the value
# then lives in state) or create the secret first and set it out of band (see README):
#   terraform apply -target=aws_secretsmanager_secret.gemini_api_key
#   aws secretsmanager put-secret-value --secret-id invoiceai-prod/gemini-api-key --secret-string "<key>"
resource "aws_secretsmanager_secret" "gemini_api_key" {
  name                    = "${local.name}/gemini-api-key"
  description             = "Gemini API key used by the worker"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "gemini_api_key" {
  # count cannot depend on a sensitive value; whether it is empty is not secret.
  count = nonsensitive(var.gemini_api_key != "") ? 1 : 0

  secret_id     = aws_secretsmanager_secret.gemini_api_key.id
  secret_string = var.gemini_api_key
}

# JSON with public_key, secret_key and host.
# - With enable_monitoring_host (default), Terraform fills it with the keys of the self-hosted
#   Langfuse on the monitoring host (monitoring_host.tf).
# - Otherwise populate it yourself, then set enable_langfuse = true:
#   aws secretsmanager put-secret-value --secret-id invoiceai-prod/langfuse \
#     --secret-string '{"public_key":"pk-...","secret_key":"sk-...","host":"https://langfuse.example.com"}'
resource "aws_secretsmanager_secret" "langfuse" {
  name                    = "${local.name}/langfuse"
  description             = "Langfuse credentials for worker LLM tracing"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "langfuse" {
  count = var.enable_monitoring_host ? 1 : 0

  secret_id = aws_secretsmanager_secret.langfuse.id
  secret_string = jsonencode({
    public_key = local.langfuse_public_key
    secret_key = local.langfuse_secret_key
    host       = "http://${local.monitoring_dns}:3002"
  })
}
