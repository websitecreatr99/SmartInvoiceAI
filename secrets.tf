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

# Only the secret container is created here; set the value out of band so the key never lands in state:
#   aws secretsmanager put-secret-value --secret-id invoiceai-prod/gemini-api-key --secret-string "<key>"
resource "aws_secretsmanager_secret" "gemini_api_key" {
  name                    = "${local.name}/gemini-api-key"
  description             = "Gemini API key used by the worker"
  recovery_window_in_days = 7
}

# JSON with public_key, secret_key and host. Populate it, then set enable_langfuse = true:
#   aws secretsmanager put-secret-value --secret-id invoiceai-prod/langfuse \
#     --secret-string '{"public_key":"pk-...","secret_key":"sk-...","host":"https://langfuse.example.com"}'
resource "aws_secretsmanager_secret" "langfuse" {
  name                    = "${local.name}/langfuse"
  description             = "Langfuse credentials for worker LLM tracing"
  recovery_window_in_days = 7
}
