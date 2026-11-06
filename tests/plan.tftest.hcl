# Offline plan test: every provider is mocked, so no AWS credentials or account are needed.
#   terraform init && terraform test
# Under mocks, computed resource attributes (ARNs, ids) stay unknown during plan, so the asserts
# only check values that come from configuration.

mock_provider "aws" {
  # IAM roles and bucket policies validate their JSON even under mocks.
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}
mock_provider "random" {}
mock_provider "archive" {}

# Mocked data sources return empty or random values; give the ones that feed expressions such as
# slice() something realistic.
override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["ap-south-1a", "ap-south-1b"]
  }
}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
  }
}

override_data {
  target = data.aws_ssm_parameter.al2023
  values = {
    value          = "ami-0123456789abcdef0"
    insecure_value = "ami-0123456789abcdef0"
  }
}

variables {
  api_image_tag       = "test-api"
  worker_image_tag    = "test-worker"
  frontend_image_tag  = "test-frontend"
  tracking_source_dir = "tests/fixtures/tracking"
}

run "plan" {
  command = plan

  variables {
    gemini_api_key = "test-gemini-key"
  }

  assert {
    condition     = aws_ecs_task_definition.worker.memory == "8192" && aws_ecs_task_definition.worker.cpu == "2048"
    error_message = "Worker task should default to 2 vCPU / 8 GB."
  }

  # The listener's target_group_arn is unknown under mocks, so check the routing structurally:
  # the HTTP listener forwards, the only target group is the frontend's on :3000, the frontend
  # service registers into it and the API service is no longer behind the ALB.
  assert {
    condition     = aws_lb_listener.http.default_action[0].type == "forward"
    error_message = "Without a certificate the HTTP listener should forward."
  }

  assert {
    condition     = aws_lb_target_group.frontend.port == 3000 && aws_lb_target_group.frontend.health_check[0].path == "/"
    error_message = "Frontend target group should be :3000 with health path /."
  }

  assert {
    condition     = one(aws_ecs_service.frontend.load_balancer).container_name == "frontend" && one(aws_ecs_service.frontend.load_balancer).container_port == 3000
    error_message = "Frontend service should register its frontend:3000 container with the ALB."
  }

  assert {
    condition     = length(aws_ecs_service.api.load_balancer) == 0
    error_message = "API service must not be behind the ALB."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.worker_queue_backlog.dimensions["Queue"] == "invoice.jobs" && aws_cloudwatch_metric_alarm.worker_queue_backlog.namespace == "AWS/AmazonMQ"
    error_message = "Worker scale-out alarm should watch invoice.jobs in AWS/AmazonMQ."
  }

  assert {
    condition     = length(aws_appautoscaling_policy.worker_scale_out.step_scaling_policy_configuration[0].step_adjustment) == 3
    error_message = "Worker scale-out should have three steps."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.worker_queue_idle.evaluation_periods == 10 && aws_cloudwatch_metric_alarm.worker_queue_idle.metric_name == "MessageCount"
    error_message = "Worker scale-in should require 10 empty minutes of MessageCount."
  }

  assert {
    condition     = length(aws_secretsmanager_secret_version.gemini_api_key) == 1
    error_message = "Passing gemini_api_key should create a secret version."
  }

  assert {
    condition     = length(aws_instance.monitoring) == 1 && aws_instance.monitoring[0].metadata_options[0].http_tokens == "required"
    error_message = "Monitoring host should exist and require IMDSv2."
  }

  assert {
    condition     = length(aws_secretsmanager_secret_version.langfuse) == 1
    error_message = "The monitoring host should fill the worker's Langfuse secret."
  }
}

run "plan_without_monitoring_host" {
  command = plan

  variables {
    enable_monitoring_host = false
  }

  assert {
    condition     = length(aws_instance.monitoring) == 0 && length(aws_s3_bucket.artifacts) == 0
    error_message = "No monitoring host resources when it is disabled."
  }

  assert {
    condition     = length(aws_secretsmanager_secret_version.gemini_api_key) == 0
    error_message = "No Gemini secret version without gemini_api_key."
  }
}
