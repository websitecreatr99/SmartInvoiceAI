variable "project" {
  description = "Short project name, used as a prefix for every resource."
  type        = string
  default     = "invoiceai"
}

variable "environment" {
  description = "Deployment environment (prod, staging...)."
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-south-1"
}

# --- Network ---------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "Number of Availability Zones to spread subnets across (>= 2 for the ALB)."
  type        = number
  default     = 2
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway for all private subnets (cheaper) instead of one per AZ (HA)."
  type        = bool
  default     = true
}

# --- Images ----------------------------------------------------------------

variable "api_image_tag" {
  description = "Tag (commit SHA) of the API image in ECR used for the initial task definition. CI replaces it on every deploy."
  type        = string
}

variable "worker_image_tag" {
  description = "Tag (commit SHA) of the worker image in ECR used for the initial task definition. CI replaces it on every deploy."
  type        = string
}

# --- API service -----------------------------------------------------------

variable "api_cpu" {
  description = "Fargate CPU units for the API task."
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Fargate memory (MiB) for the API task."
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Number of API tasks. Job storage is on EFS, so more than one is possible once job_store is safe for concurrent writers."
  type        = number
  default     = 1
}

variable "cors_origins" {
  description = "Comma-separated origins allowed by the API's CORS policy (the frontend URL)."
  type        = string
  default     = "http://localhost:3000"
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS on the ALB. Leave empty to serve plain HTTP only."
  type        = string
  default     = ""
}

# --- Worker service --------------------------------------------------------

variable "worker_cpu" {
  description = "Fargate CPU units for a worker task (OCR is CPU heavy)."
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Fargate memory (MiB) for a worker task."
  type        = number
  default     = 4096
}

variable "worker_min_count" {
  description = "Minimum number of worker tasks."
  type        = number
  default     = 1
}

variable "worker_max_count" {
  description = "Maximum number of worker tasks."
  type        = number
  default     = 20
}

variable "worker_cpu_target" {
  description = "Average CPU utilisation (%) the worker autoscaler aims for."
  type        = number
  default     = 60
}

variable "worker_use_spot" {
  description = "Run workers on Fargate Spot. Interrupted jobs are re-queued by RabbitMQ because the worker acks only after finishing."
  type        = bool
  default     = false
}

# --- RabbitMQ (Amazon MQ) --------------------------------------------------

variable "mq_instance_type" {
  description = "Amazon MQ broker instance type."
  type        = string
  default     = "mq.m5.large"
}

variable "mq_deployment_mode" {
  description = "SINGLE_INSTANCE or CLUSTER_MULTI_AZ."
  type        = string
  default     = "SINGLE_INSTANCE"

  validation {
    condition     = contains(["SINGLE_INSTANCE", "CLUSTER_MULTI_AZ"], var.mq_deployment_mode)
    error_message = "mq_deployment_mode must be SINGLE_INSTANCE or CLUSTER_MULTI_AZ."
  }
}

variable "mq_username" {
  description = "RabbitMQ admin username (\"guest\" is not allowed by Amazon MQ)."
  type        = string
  default     = "invoiceai"
}

# --- Observability ---------------------------------------------------------

variable "log_retention_days" {
  description = "CloudWatch log retention for the ECS services."
  type        = number
  default     = 30
}

variable "enable_langfuse" {
  description = "Inject Langfuse keys into the worker from the langfuse secret (populate it before enabling)."
  type        = bool
  default     = false
}

variable "enable_managed_prometheus" {
  description = "Create an Amazon Managed Service for Prometheus workspace for the monitoring stack to remote-write into."
  type        = bool
  default     = false
}

# --- CI/CD -----------------------------------------------------------------

variable "github_repo" {
  description = "GitHub repository (owner/name) allowed to deploy through OIDC."
  type        = string
  default     = "kishannextq/hackathon"
}

variable "github_deploy_branches" {
  description = "Branches whose workflows may assume the deploy role."
  type        = list(string)
  default     = ["fastapi", "worker"]
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false if the account already has one."
  type        = bool
  default     = true
}
