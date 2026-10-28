# InvoiceAI on AWS (ECS Fargate)

Terraform for the application side of production: the API (fastapi branch) and worker (worker branch)
on ECS Fargate, plus everything they depend on. Prometheus, Grafana and Langfuse stay in the
monitoring repository and plug in through the outputs listed below.

```
Internet ──► ALB (public subnets) ──► API service :5000 ──┐
                                        │ EFS /app/storage │
                                        ▼                  ▼
                               Amazon MQ (RabbitMQ, amqps:5671)
                                        ▲
                               Worker service :9100 (autoscaled 1..20)
                                        │
                                        ▼ Gemini / Langfuse via NAT
```

| File | What it creates |
|------|-----------------|
| `network.tf` | VPC, public/private subnets across 2 AZs, NAT, security groups |
| `ecr.tf` | `invoiceai-api` and `invoiceai-worker` repositories (immutable tags, scan on push) |
| `mq.tf` | Amazon MQ for RabbitMQ (replaces the rabbitmq container) |
| `efs.tf` | Encrypted EFS + access point for the API's job storage |
| `secrets.tf` | Secrets Manager: RabbitMQ URL (generated), Gemini key, Langfuse keys |
| `alb.tf` | Application Load Balancer, `/health` target group, optional HTTPS |
| `ecs.tf` | Cluster, log groups, execution and task IAM roles |
| `services.tf` | API and worker task definitions, services, worker CPU autoscaling |
| `monitoring.tf` | Cloud Map DNS for Prometheus scraping, optional Managed Prometheus |
| `github_oidc.tf` | GitHub OIDC provider and the deploy role used by both branches' CI |

## Bootstrap order

The repositories have to exist and hold an image before the services can start.

```bash
# from the root of this branch (the .tf files live at the top level)
cp terraform.tfvars.example terraform.tfvars    # edit values
terraform init

# 1. Create only the registries.
terraform apply -target=aws_ecr_repository.app

# 2. Push one image from each branch, tagged with its commit SHA, and put the SHAs
#    into api_image_tag / worker_image_tag.

# 3. Create everything else.
terraform apply

# 4. Set the secret values Terraform deliberately does not store in state.
aws secretsmanager put-secret-value --secret-id invoiceai-prod/gemini-api-key --secret-string "<key>"
```

After that, CI owns deployments: each branch builds its image, registers a new task definition
revision and updates its service. Terraform ignores `task_definition` on both services (and
`desired_count` on the worker), so a later `terraform apply` never rolls back an image.

## CI (per branch)

```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: <github_deploy_role_arn output>
      aws-region: ap-south-1
  - uses: aws-actions/amazon-ecr-login@v2
  # docker build/push <ecr url>:${{ github.sha }}
  # aws ecs describe-task-definition --task-definition invoiceai-prod-api   (or -worker)
  - uses: aws-actions/amazon-ecs-render-task-definition@v1
  - uses: aws-actions/amazon-ecs-deploy-task-definition@v2
    with:
      service: invoiceai-prod-api        # or invoiceai-prod-worker
      cluster: invoiceai-prod-cluster
      wait-for-service-stability: true
```

## Monitoring repository inputs

Run Prometheus, Grafana and Langfuse as separate ECS services in the same cluster with:

- `vpc_id`, `private_subnet_ids`, and `monitoring_security_group_id` (already allowed to scrape)
- Scrape targets via DNS service discovery: `api.invoiceai.local:5000`, `worker.invoiceai.local:9100`
- `prometheus_remote_write_url` if `enable_managed_prometheus = true`

## Things to check

- **AMQPS:** Amazon MQ only accepts TLS on 5671, so `RABBITMQ_URL` is `amqps://...`. Make sure the
  broker client in `broker.py` / `worker.py` handles an `amqps` URL.
- **Graceful shutdown:** Fargate caps `stopTimeout` at 120s (k8s used 600s). A PDF still processing
  after that is re-queued by RabbitMQ, because the worker acks only after it finishes.
- **Scaling:** workers scale on CPU instead of queue length (the KEDA setup). OCR is CPU-bound, so
  this follows load well; queue-depth step scaling on the Amazon MQ `MessageCount` metric can be
  added later.
- **API replicas:** EFS is shared storage, but keep `api_desired_count = 1` until `job_store` is
  safe with several writers.
- **Upload bucket (not created yet):** the API and worker now send files through object storage
  when `STORAGE_BUCKET` is set, and otherwise inline as base64 inside the RabbitMQ message. This
  Terraform creates no bucket and sets no `STORAGE_BUCKET`, so on ECS whole documents travel
  through Amazon MQ. To fix it, add an S3 bucket with a lifecycle rule that expires `uploads/`,
  grant the API task role `s3:PutObject`/`DeleteObject` and the worker task role `s3:GetObject` on
  it, and set `STORAGE_BUCKET` on both services.
- **Hung-job timeout vs. stopTimeout:** the worker's `JOB_TIMEOUT_SECONDS` defaults to 540s, which
  is longer than Fargate's 120s `stopTimeout`. Nothing breaks (the message is redelivered), but a
  job stopped by a deploy counts towards `MAX_REDELIVERIES`. Consider lowering `OCR_DPI` or setting
  the worker's limits (`MAX_PAGES`, `JOB_TIMEOUT_SECONDS`) in `services.tf` for this environment.
