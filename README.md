# InvoiceAI on AWS (ECS Fargate)

Terraform for the whole production system: the frontend (frontend branch), API (fastapi branch)
and worker (worker branch) on ECS Fargate, plus everything they depend on, and a monitoring host
that runs the tracking branch's docker compose stack (Prometheus, Grafana, Loki, Langfuse).

## Other deployment targets

| Target | Where | Status |
|--------|-------|--------|
| AWS ECS Fargate | this README (`*.tf` at the top level) | Paid; not deployed |
| Render (free) + Vercel (free) | `lite` and `frontend` branches | **Live.** API with the worker running in-process and Gemini doing the OCR, so no RabbitMQ and about 110 MB of RAM. Backend https://hackathon-elnx.onrender.com, frontend https://hackathon-frontend-gamma-seven.vercel.app. Deployment steps are in those branches' READMEs |
| Hugging Face Space + Vercel | [`huggingface/`](huggingface/README.md) | Not usable for free any more: Docker Spaces now need a paid plan |
| Oracle Cloud Always Free VM | [`oracle/`](oracle/README.md) | Works, but Oracle needs a credit card to sign up |

```
Internet ──► ALB :80/:443 (public subnets)
               │
               ▼
        Frontend service :3000 (Next.js) ── /api/* proxy ──► api.invoiceai.local:5000 (Cloud Map)
                                                                │
                                         ┌──────────────────────┤ EFS /app/storage
                                         ▼                      ▼
                              S3 uploads bucket ◄──── API service :5000
                              (uploads/, 1 day)                 │ publish job (file key)
                                         │                      ▼
                                         │        Amazon MQ (RabbitMQ, amqps:5671), queue invoice.jobs
                                         │                      │ CloudWatch MessageReadyCount / MessageCount
                                         ▼                      ▼
                              Worker service :9100 (scales 1..20 on queue depth) ──► Gemini via NAT
                                         │
                                         ▼ traces (Langfuse :3002), logs (FireLens -> Loki :3500)
                              Monitoring host (EC2, private, SSM only): monitoring.invoiceai.local
                              Prometheus :9090, Grafana :3001, Loki/Alloy, Langfuse :3002,
                              CloudWatch exporter (Amazon MQ metrics)
```

All tasks and the monitoring host run in private subnets. S3 traffic uses a gateway VPC endpoint;
everything else leaves through the NAT gateway.

| File | What it creates |
|------|-----------------|
| `network.tf` | VPC, public/private subnets across 2 AZs, NAT, S3 gateway endpoint, security groups |
| `ecr.tf` | `invoiceai-api`, `invoiceai-worker` and `invoiceai-frontend` repositories (immutable tags, scan on push) |
| `mq.tf` | Amazon MQ for RabbitMQ (replaces the rabbitmq container) |
| `efs.tf` | Encrypted EFS + access point for the API's job storage |
| `s3.tf` | Private, encrypted uploads bucket; `uploads/` expires after 1 day |
| `secrets.tf` | Secrets Manager: RabbitMQ URL (generated), Gemini key, Langfuse keys |
| `alb.tf` | Application Load Balancer → frontend target group (`/` health check), optional HTTPS |
| `ecs.tf` | Cluster, log groups, execution role, task roles (EFS/S3 for the API, S3 + task protection for the worker) |
| `services.tf` | Frontend, API and worker task definitions and services, FireLens logging, worker queue-depth autoscaling |
| `monitoring.tf` | Cloud Map namespace `invoiceai.local` (api, worker, frontend), optional Managed Prometheus |
| `monitoring_host.tf` | EC2 monitoring host running the tracking stack, its bundle bucket, generated credentials, `monitoring.invoiceai.local` |
| `monitoring_user_data.sh.tftpl` | Boot script: Docker + Compose, unpack the bundle, write `.env`, `docker compose up` |
| `github_oidc.tf` | GitHub OIDC provider and the deploy role used by the fastapi, worker and frontend CI |
| `tests/plan.tftest.hcl` | Offline `terraform test` with mocked providers |

## Bootstrap order

The repositories have to exist and hold an image, and the Gemini secret has to hold a value,
before the services can start.

```bash
# from the root of this branch (the .tf files live at the top level)
cp terraform.tfvars.example terraform.tfvars    # edit values
git worktree add ../tracking origin/tracking   # the monitoring host's stack (tracking_source_dir)
terraform init

# 1. Create the registries and the Gemini secret container.
terraform apply -target=aws_ecr_repository.app -target=aws_secretsmanager_secret.gemini_api_key

# 2. Put the Gemini key into the secret (kept out of Terraform state).
aws secretsmanager put-secret-value --secret-id invoiceai-prod/gemini-api-key --secret-string "<key>"
#    Alternative: skip this and pass the key to Terraform instead (it is then stored in state):
#    export TF_VAR_gemini_api_key="<key>"

# 3. Push one image from each branch (fastapi -> invoiceai-api, worker -> invoiceai-worker,
#    frontend -> invoiceai-frontend), tagged with its commit SHA, and put the SHAs into
#    api_image_tag / worker_image_tag / frontend_image_tag.

# 4. Create everything else.
terraform apply
terraform output app_url
```

After that, CI owns deployments: each branch builds its image, registers a new task definition
revision and updates its service. Terraform ignores `task_definition` on all three services (and
`desired_count` on the worker), so a later `terraform apply` never rolls back an image.

The frontend image must be built with its `/api/*` proxy pointing at
`http://api.invoiceai.local:5000`; the API has no public endpoint of its own.

## Monitoring host (Grafana, Langfuse, Prometheus)

With `enable_monitoring_host = true` (default), Terraform zips `tracking_source_dir`, uploads it to
a private artifacts bucket and starts an EC2 instance that runs
`docker compose -f docker-compose.yml -f docker-compose.aws.yml --profile langfuse up -d`.
Changing any file in the tracking checkout and re-applying replaces the instance.

- Credentials (Grafana admin, Langfuse admin and internal passwords, Langfuse API keys) are
  generated and stored in the `invoiceai-prod/monitoring` secret. The worker's `invoiceai-prod/langfuse`
  secret is filled automatically and points at `http://monitoring.invoiceai.local:3002`.
- ECS logs go to Loki through a FireLens (Fluent Bit) sidecar in each task, labelled
  `service=api|worker|frontend`. With the monitoring host disabled they go to CloudWatch Logs.
- There is no public IP or SSH. Open the UIs with SSM port forwarding (install the
  [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)):

```bash
terraform output monitoring_port_forward_commands
# e.g. Grafana:
aws ssm start-session --target <monitoring_instance_id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=3001,localPortNumber=3001
# then open http://localhost:3001 (Langfuse: 3002, Prometheus: 9090)

# Logins: Grafana user "admin", Langfuse user admin@invoiceai.local
aws secretsmanager get-secret-value --secret-id invoiceai-prod/monitoring \
  --query SecretString --output text | jq '{GRAFANA_ADMIN_PASSWORD, LANGFUSE_ADMIN_PASSWORD}'
```

Boot logs are in `/var/log/cloud-init-output.log` on the host (`aws ssm start-session --target <id>`).

## CI (per branch)

The fastapi, worker and frontend branches each deploy their own service with the same role.
Set these **repository variables** (Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|----------|-------|
| `AWS_DEPLOY_ROLE_ARN` | `terraform output -raw github_deploy_role_arn` |
| `AWS_REGION` (optional) | defaults to `ap-south-1` in the workflows |

| Branch | ECR repository | Task family / service |
|--------|----------------|-----------------------|
| fastapi | `invoiceai-api` | `invoiceai-prod-api` |
| worker | `invoiceai-worker` | `invoiceai-prod-worker` |
| frontend | `invoiceai-frontend` | `invoiceai-prod-frontend` |

```yaml
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}
      aws-region: ${{ vars.AWS_REGION || 'ap-south-1' }}
  - uses: aws-actions/amazon-ecr-login@v2
  # docker build/push <ecr url>:${{ github.sha }}
  # aws ecs describe-task-definition --task-definition invoiceai-prod-<api|worker|frontend>
  - uses: aws-actions/amazon-ecs-render-task-definition@v1
  - uses: aws-actions/amazon-ecs-deploy-task-definition@v2
    with:
      service: invoiceai-prod-<api|worker|frontend>
      cluster: invoiceai-prod-cluster
      wait-for-service-stability: true
```

## Testing

`tests/plan.tftest.hcl` plans the whole stack against mocked `aws`, `random` and `archive`
providers (Terraform >= 1.7), so it needs no AWS account:

```bash
terraform init -backend=false
terraform validate
terraform test
```

## Things to check

- **Worker scaling:** workers scale out on `MessageReadyCount > 0` for `invoice.jobs` (+1/+3/+5
  by backlog) and back to `worker_min_count` after `MessageCount` has been 0 for 10 minutes. This
  relies on Amazon MQ publishing per-queue CloudWatch metrics (dimensions Broker, VirtualHost,
  Queue). Check in CloudWatch that they appear after the first job; missing data never scales in.
- **Scale-in protection:** the worker must call `UpdateTaskProtection` while it processes a job
  (the task role allows it), otherwise a scale-in can stop a busy task. A stopped job is still
  re-queued, because the worker acks only after it finishes.
- **Graceful shutdown on deploys:** Fargate caps `stopTimeout` at 120s, while the worker's
  `JOB_TIMEOUT_SECONDS` defaults to 540s. A job cut off by a deploy is redelivered but counts
  towards `MAX_REDELIVERIES`.
- **Worker memory:** 8 GB with `OCR_DPI=200`. PaddleOCR needs more than 5 GB at 300 DPI; raise
  `worker_memory` before raising `ocr_dpi`.
- **API replicas:** EFS is shared storage, but keep `api_desired_count = 1` until `job_store` is
  safe with several writers.
- **Monitoring host is a single instance:** if it is down, Langfuse traces and Loki logs are lost
  for that time (the app keeps running; Fluent Bit retries for a while). Prometheus, Loki and
  Langfuse data live on its 50 GB root volume and are lost when the instance is replaced, e.g. by a
  change to the tracking checkout. Disable it with `enable_monitoring_host = false` to fall back
  to CloudWatch Logs.
- **`gemini_api_key` variable:** convenient, but the key ends up in Terraform state. Prefer the
  `-target` + `put-secret-value` route above with a shared state backend.
