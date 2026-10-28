# 📄 InvoiceAI API

InvoiceAI extracts **structured data** from **unstructured business documents** (invoices, purchase orders and similar) using **OCR + an LLM (Gemini)**. Either it fills the invoice schema (header + line items), or it pulls just the columns you name. Every value cites the document line it came from.

This branch is the **API**. The other parts of the system live on their own branches:

| Branch | What |
|--------|------|
| `fastapi` (this one) | HTTP API: accepts uploads, queues work, collects results |
| `worker` | OCR + LLM extraction pods that consume the queue |
| `frontend` | Next.js web UI (talks to this API through `/api/*`) |
| `tracking` | Prometheus, Loki, Grafana and Langfuse |
| `infra` | Terraform for AWS (ECS Fargate, Amazon MQ, EFS) |

---

## 🚀 Getting Started

### 1️⃣ Clone the repository

    git clone https://github.com/kishannextq/hackathon.git
    cd hackathon
    git checkout fastapi

### 2️⃣ Create `.env`

Create a `.env` file next to `docker-compose.yml`. The worker containers read it:

    GOOGLE_API_KEY=your_gemini_api_key

🔑 Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/). Use the name `GOOGLE_API_KEY`: that's the variable the Gemini client reads. (The Kubernetes Secret stores it as `GEMINI_API_KEY`, and the worker Deployment exposes it under both names.)

Optional, in the same file: `STORAGE_BUCKET` and `AWS_*` credentials (plus `S3_ENDPOINT_URL` for MinIO / GCS / R2) to send files through object storage, and the `LANGFUSE_*` keys from the `tracking` branch for LLM tracing.

### 3️⃣ Run everything

    docker compose up -d --build

This starts RabbitMQ, the API on port 5000, and two worker pods (image `ghcr.io/kishannextq/hackathon-worker:latest`, built by the `worker` branch's CI; set `WORKER_IMAGE` to use a local build). Add workers with `docker compose up -d --scale worker=4`. RabbitMQ's dashboard is at http://localhost:15672 (guest/guest).

Then start the web UI from the `frontend` branch (`npm install && npm run dev`, http://localhost:3000) and, optionally, the monitoring stack from the `tracking` branch.

To run just the API locally (Python 3.11, as in the Dockerfile):

    pip install -r requirements.txt
    RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F python app.py

Without a reachable RabbitMQ the API still starts: `/health` and `/upload` work, `/jobs` and `/process` return 503, and the result consumer keeps retrying every 5 s.

---

## ⚖️ Architecture

The slow work (OCR + LLM extraction) runs on the `worker` branch's pods:

    client ──> API ──publish──> RabbitMQ [invoice.jobs] ──> worker pod 1..N  (OCR + Gemini)
                 ^                                               │
                 └──consume── RabbitMQ [invoice.results] <───────┘

- Every document becomes one message, so a bulk upload fans out across all worker pods; RabbitMQ gives each pod one document at a time.
- Messages are durable and only acknowledged after processing, so a crashed pod's document is retried by another.
- **Files go through object storage, not RabbitMQ.** With `STORAGE_BUCKET` set (S3, or MinIO / GCS / R2 via `S3_ENDPOINT_URL`), uploads are stored at `uploads/<job_id>/<filename>` and messages carry only the key. Without it files travel inline as base64, which is fine for tests and a laptop but makes RabbitMQ hold whole documents in memory. Give the bucket a lifecycle rule that expires `uploads/`.
- Temporary failures are retried through `invoice.jobs.retry`, and documents that keep crashing workers end up in `invoice.jobs.dlq` with an error result sent back, so every job still finishes. `queues.py` declares this topology and must stay identical to `src/queues.py` on the `worker` branch.
- The API stays fast and light: it never runs OCR, and its image has no ML dependencies.
- Job state lives in `STORAGE_DIR`. Running several API replicas requires that directory on shared (ReadWriteMany) storage.

### ⚙️ Settings

| Variable | Default | Meaning |
|----------|---------|---------|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/%2F` | Broker connection |
| `JOBS_QUEUE` / `RESULTS_QUEUE` | `invoice.jobs` / `invoice.results` | Queue names (must match the worker) |
| `RETRY_QUEUE` / `DEAD_LETTER_QUEUE` | `<jobs>.retry` / `<jobs>.dlq` | Retry and dead-letter queues |
| `RETRY_DELAY_SECONDS` / `MAX_REDELIVERIES` | 30 / 2 | Part of the queue declaration; must match the worker |
| `STORAGE_DIR` | `storage` | Job state and results |
| `STORAGE_BUCKET` / `S3_ENDPOINT_URL` | – | Object storage for uploads (see above) |
| `MAX_FILE_MB` | 25 | Larger uploads get a 413 |
| `MAX_FILES_PER_JOB` | 100 | More files in one `/jobs` call get a 413 |
| `PROCESS_TIMEOUT` | 600 | Seconds `/process` waits before returning the `job_id` to poll |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `RESULT_CONSUMER` | 1 | `0` disables the result consumer (tests) |

### ☸️ Kubernetes

    cp k8s/secret.example.yaml k8s/secret.yaml   # fill in values
    kubectl apply -f k8s/secret.yaml -f k8s/rabbitmq.yaml -f k8s/api.yaml

Worker Deployment and autoscaling manifests are on the `worker` branch (`k8s/`). For AWS ECS, see the `infra` branch.

**Upgrading a deployment from before the quorum queue.** RabbitMQ can't change an existing queue's type, and old and new services can't share `invoice.jobs`. Scale the workers to 0, run `RABBITMQ_URL=... python scripts/migrate_queues.py` (it parks queued jobs, recreates the queues and moves the jobs back; safe to re-run), then deploy the new API and worker images. New jobs get a 503 between the migration and the new API rollout.

### 🧪 Tests & CI/CD

`pip install -r requirements-dev.txt && pytest` runs the unit tests. With `RABBITMQ_URL` set it also runs 3 integration tests that push a 12-PDF job through a real broker to three fake workers and check the load is shared (they are skipped otherwise).

`scripts/fake_worker.py` speaks the worker's queue protocol without OCR or an LLM, which is handy for testing the API against a real RabbitMQ: `RABBITMQ_URL=... python scripts/fake_worker.py`.

GitHub Actions (`.github/workflows/ci.yml`) on `fastapi`: unit + RabbitMQ integration tests → image build → container smoke test through RabbitMQ (`scripts/smoke_test.sh`) → publish `ghcr.io/<owner>/<repo>-api` (pushes only).

---

## 🖥️ Usage

Interactive API docs are at [http://127.0.0.1:5000/docs](http://127.0.0.1:5000/docs).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/jobs` | Queue documents and return `202` with a `job_id` immediately. Used by the web UI. Each call is its own job |
| GET | `/jobs/{job_id}` | `queued` → `processing` (with progress) → `done`; results appear in upload order as each file finishes |
| POST | `/upload` | Legacy: save PDFs (multipart field `pdfs`) into `data/` for `/process` |
| POST | `/delete` | Legacy: remove an uploaded PDF (`{"filename": "..."}`) |
| POST | `/process` | Legacy: send the PDFs in `data/` to the workers and wait for the results |
| GET | `/health` | Liveness check |
| GET | `/metrics` | Prometheus metrics for the `tracking` branch stack |

**`POST /jobs`** takes multipart `files` (`pdfs` is still accepted) and an optional `columns` form field: a JSON list (`["PO number", "Total"]`) or names separated by commas or new lines, up to 50 names of up to 100 characters each. Without `columns` the invoice schema is used.

Accepted file types: PDFs and images (`.pdf .png .jpg .jpeg .tif .tiff .bmp .webp`) are OCR'd; `.txt .csv .tsv .md .json .xml .html .htm .docx` are read as text. Other files are skipped and listed in the response; duplicate names get a ` (2)` suffix.

    {"job_id": "…", "status": "queued", "files": ["a.pdf", "b.png"], "skipped": ["notes.zip"], "columns": []}

**`GET /jobs/{job_id}`**:

    {
      "job_id": "…", "status": "processing", "progress": {"done": 1, "total": 2},
      "files": ["a.pdf", "b.png"], "columns": [],
      "results": [{"filename": "a.pdf", "structured_data": {"extraction": [...]}, "fields": {"columns": [...], "rows": [...]}}]
    }

- `fields` is a table for every result: `columns` plus `rows` whose cells are `{"value": …, "source": {"page", "line", "text", "confidence"} | null}`.
- `structured_data` (header + line items) is present only when no `columns` were given.
- A failed file comes back as `{"filename": …, "error": "…"}`.

**Metrics** (`/metrics`): `invoiceai_api_requests_total` and `invoiceai_api_request_duration_seconds` by route, `invoiceai_api_jobs_submitted_total`, `invoiceai_api_pdfs_submitted_total`, `invoiceai_api_publish_failures_total`, `invoiceai_api_results_received_total`, `invoiceai_api_job_duration_seconds`.

---

## 📸 Preview Screenshot
<p align="center">
  <img src="assets/Screenshot 2025-08-28 125448.png" alt="InvoiceAI Preview" width="700">
</p>

---

## 📂 Project Structure

    .
    ├── app.py              # FastAPI app
    ├── broker.py           # RabbitMQ publisher + result consumer
    ├── queues.py           # Queue topology shared with the worker
    ├── object_store.py     # Uploads files to the bucket for the workers
    ├── job_store.py        # Job state and results on disk
    ├── metrics.py          # Prometheus metrics
    ├── docker-compose.yml  # RabbitMQ + API + worker pods
    ├── k8s/                # RabbitMQ, API, secret template
    ├── scripts/            # Container smoke test, fake worker for tests, queue migration
    ├── tests/              # Unit, metrics and RabbitMQ integration tests
    ├── templates/, static/ # Old server-rendered UI, no longer served (the UI is on the `frontend` branch)
    ├── data/, output/, structured_output/  # Sample documents and example OCR / extraction output
    ├── research/           # Notebook from the original prototype
    ├── requirements.txt    # API dependencies (no ML libraries)
    └── .env                # Your Gemini API key (git-ignored)

---

## ✅ Features
- 📂 Bulk upload: PDFs, images, text documents and `.docx`, one job per upload
- 🧾 Invoice schema (header + line items) or your own columns
- 🔎 Every extracted value cites its source page and line
- ⚖️ Spreads work across any number of worker pods, with retries and a dead-letter queue
- 📈 Prometheus metrics, plus Langfuse tracing on the workers

---

## 📜 License
This project is licensed under the **MIT License**.
Free to use and modify.
