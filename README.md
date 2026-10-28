# 📄 InvoiceAI Worker

The slow half of InvoiceAI: it takes documents off a RabbitMQ queue, reads them (**OCR with PaddleOCR** for PDFs and images, direct text extraction for everything else), runs **LLM extraction (Gemini)**, and publishes the result back. The API that accepts uploads and sends jobs here lives on the `fastapi` branch.

## What it extracts

| Input | How it's read |
|-------|---------------|
| `.pdf .png .jpg .jpeg .tif .tiff .bmp .webp` | OCR (PDFs rendered one page at a time) |
| `.txt .csv .tsv .md .json .xml .html .htm` | Read as text (HTML tags stripped), no OCR |
| `.docx` | Paragraph text read directly, no OCR |

- **No `columns` in the job:** Gemini fills the invoice schema (header + line items, `src/pydantic_schema.py`), which is validated before it's returned as `structured_data`.
- **With `columns`:** Gemini extracts only those fields from line-numbered text and cites the line each value came from.
- Either way the result carries `fields`: table rows whose cells are `{"value": …, "source": {"page", "line", "text", "confidence"} | null}` (`src/sources.py`), so the UI can show where every value was read.

---

## ⚖️ How it scales

    fastapi (API) ──publish──> [invoice.jobs] ──> worker pod 1
                                              ──> worker pod 2      (one PDF per message)
                                              ──> worker pod N
    fastapi (API) <──consume── [invoice.results] <── every pod

- **Load balancing is done by RabbitMQ.** Every pod consumes from the same queue; each message goes to exactly one pod, and `prefetch=1` means a pod only takes a new PDF once it has finished the last. A bulk upload of 50 PDFs spreads across all available pods instead of queueing behind one.
- **No work is lost.** A message is acked only after its result is published. If a pod crashes or is scaled down mid-job, RabbitMQ hands the PDF to another pod.
- **Temporary failures are retried, bad documents are not.** A Gemini 429/5xx or object-storage outage (after the clients' own backoff) sends the job to `invoice.jobs.retry`, which feeds it back into `invoice.jobs` after `RETRY_DELAY_SECONDS`, up to `MAX_ATTEMPTS` tries. Unreadable or invalid documents fail at once with an error result.
- **A poison document can't take the fleet down.** `invoice.jobs` is a quorum queue that counts deliveries. When a message has already crashed, OOM-killed or hung pods `MAX_REDELIVERIES` times, the next pod moves it to `invoice.jobs.dlq` and publishes an error result, so the API still hears back.
- **Every job is bounded.** Files over `MAX_FILE_MB` and PDFs over `MAX_PAGES` are refused before OCR; PDFs are rendered one page at a time; Gemini calls time out after `LLM_TIMEOUT_SECONDS`. A job still running after `JOB_TIMEOUT_SECONDS` is treated as hung: the worker exits (nonzero) so the pod restarts and the delivery counts towards `MAX_REDELIVERIES`.
- **Customer data stays out of logs and traces.** Prompts, OCR text and LLM output are never logged, validation errors list field paths without values, and Langfuse receives timings, tokens and cost only (`LANGFUSE_CAPTURE_CONTENT=true` to opt in, e.g. in staging).
- **Autoscaling** adds pods while the queue is backed up and removes them when it drains (`k8s/worker-keda.yaml`).

## Message format

Job (`invoice.jobs`), one per document. The file itself lives in object storage; the message carries its key:

    {"job_id": "…", "filename": "invoice.pdf", "file_key": "uploads/<job_id>/invoice.pdf", "columns": ["optional", "…"]}

When the API runs without `STORAGE_BUCKET`, it sends the file inline as `"file_b64"` instead (the older `"pdf_b64"` is also accepted). That makes RabbitMQ hold whole files in memory, so don't do it in production. The worker adds `"attempt"` when it requeues a job for retry.

Queues must be declared with the arguments in `src/queues.py` by every service that declares them (RabbitMQ rejects a mismatched redeclare); the API's `queues.py` is an identical copy. **Migrating from a plain `invoice.jobs`**: a queue's type can't be changed in place. Scale the workers to 0 and run `scripts/migrate_queues.py` from the `fastapi` branch, which parks queued jobs, recreates the queues and moves the jobs back, before deploying the new images.

Result (`invoice.results`):

    {"job_id": "…", "filename": "invoice.pdf", "ok": true,  "structured_data": {"extraction": [...]}, "fields": {"columns": [...], "rows": [...]}}
    {"job_id": "…", "filename": "invoice.pdf", "ok": true,  "fields": {"columns": ["PO number", "…"], "rows": [...]}}   (with columns)
    {"job_id": "…", "filename": "invoice.pdf", "ok": false, "error": "…"}

---

## 🚀 Run

Locally (needs a RabbitMQ, Python 3.10/3.11, and Poppler on `PATH` for PDF rendering: `apt install poppler-utils`, `brew install poppler`, or the Windows build from oschwartz10612/poppler-windows):

    pip install -r requirements.txt
    export RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
    export GOOGLE_API_KEY=your-gemini-key
    python worker.py

The worker reads a `.env` in the working directory too. Loading PaddleOCR and LangChain can take a minute or more before it connects. Metrics are served from the start; after that it logs `Worker consuming from invoice.jobs`, or retries the broker every 5 s if it can't connect.

Docker:

    docker build -t invoiceai-worker .
    docker run -e RABBITMQ_URL=amqp://guest:guest@host.docker.internal:5672/%2F -e GOOGLE_API_KEY=… invoiceai-worker

Kubernetes:

    cp k8s/secret.example.yaml k8s/secret.yaml   # fill in RABBITMQ_URL and GEMINI_API_KEY
    kubectl apply -f k8s/secret.yaml -f k8s/worker-deployment.yaml
    kubectl apply -f k8s/worker-keda.yaml        # queue-length autoscaling (needs KEDA)
    # or: kubectl apply -f k8s/worker-hpa-cpu.yaml   (CPU autoscaling, no KEDA)

| Setting | Default | Meaning |
|---------|---------|---------|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/%2F` | Broker connection |
| `JOBS_QUEUE` / `RESULTS_QUEUE` | `invoice.jobs` / `invoice.results` | Queue names (must match the API) |
| `RETRY_QUEUE` / `DEAD_LETTER_QUEUE` | `<jobs>.retry` / `<jobs>.dlq` | Retry and dead-letter queues (must match the API) |
| `WORKER_PREFETCH` | 1 | Documents a pod holds at once; keep 1 for even spreading |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used for extraction |
| `GOOGLE_API_KEY` | – | Gemini API key (the name the Gemini client reads; the k8s Deployment maps the Secret's `GEMINI_API_KEY` onto it) |
| `STORAGE_BUCKET` | – | Bucket that `file_key` refers to |
| `S3_ENDPOINT_URL` | AWS S3 | S3-compatible endpoint (MinIO, GCS interop, R2); credentials via the standard `AWS_*` variables or IRSA |
| `MAX_FILE_MB` / `MAX_PAGES` | 25 / 30 | Larger documents are rejected before OCR |
| `OCR_DPI` | 300 | PDF render resolution; 200 is roughly 2x faster and usually enough |
| `PDF_PAGE_TIMEOUT_SECONDS` | 120 | Poppler time limit for reading page count and rendering each page |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | 120 / 3 | Per Gemini call; the client backs off between retries |
| `MAX_ATTEMPTS` / `RETRY_DELAY_SECONDS` | 3 / 30 | Queue-level retries for temporary failures |
| `MAX_REDELIVERIES` | 2 | Lost deliveries (crash, OOM, hang) before a message goes to the DLQ |
| `JOB_TIMEOUT_SECONDS` | 540 | Longer jobs are presumed hung; keep below the pod's `terminationGracePeriodSeconds` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | – / – / Langfuse Cloud | Enable Langfuse tracing |
| `LANGFUSE_CAPTURE_CONTENT` | false | Send prompts and outputs to Langfuse |
| `LLM_INPUT_USD_PER_1M` / `LLM_OUTPUT_USD_PER_1M` | 0.30 / 2.50 | Prices used for the cost metric |
| `METRICS_PORT` | 9100 | Prometheus endpoint; `0` disables |
| `ALIVE_FILE` | `<tmp>/worker-alive` | Touched every 15 s while connected; used by the Docker and k8s liveness checks |

---

## 📈 Observability

Dashboards, alerts and log collection live on the `tracking` branch. This worker feeds them:

- **Prometheus metrics** on `:9100/metrics` (`METRICS_PORT`, `0` disables), all exported at zero on startup:

  | Metric | What |
  |--------|------|
  | `invoiceai_worker_pdfs_total{status}` | Documents processed: `ok`, `error`, `retry` |
  | `invoiceai_worker_jobs_retried_total` / `invoiceai_worker_jobs_dead_lettered_total` | Jobs requeued after a temporary failure / parked in the DLQ |
  | `invoiceai_worker_pdf_duration_seconds` / `invoiceai_worker_stage_duration_seconds{stage}` | Time per document, and per stage (`ocr`, `llm`, `validate`) |
  | `invoiceai_worker_in_progress` | Documents being processed now |
  | `invoiceai_llm_calls_total` / `invoiceai_llm_latency_seconds` / `invoiceai_llm_tokens_total` / `invoiceai_llm_cost_usd_total` | Gemini calls, latency, tokens and estimated USD cost, by model |

- **Langfuse** (set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`): one trace per document, grouped into a session per job, with spans for each stage and the Gemini generation including tokens, cost and latency.
- Cost is estimated from token usage at `LLM_INPUT_USD_PER_1M` / `LLM_OUTPUT_USD_PER_1M` (defaults: Gemini 2.5 Flash list price, $0.30 / $2.50); update them if pricing or the model changes.

---

## 🧪 Tests & CI/CD

Unit tests (OCR and LLM stubbed): `pip install -r requirements-dev.txt && pytest`.

Smoke test against a live broker and running worker: `python scripts/smoke_test.py`.

GitHub Actions (`.github/workflows/ci.yml`) on `worker`: unit tests → image build → worker container + real RabbitMQ round-trip → publish `ghcr.io/<owner>/<repo>-worker` (pushes only).

---

## 📂 Project Structure

    ├── worker.py            # RabbitMQ consumer, retries, DLQ hand-off
    ├── ocr_pipeline.py      # PDF/image → PaddleOCR; Gemini prompts for the invoice schema and for custom columns
    ├── telemetry.py         # Prometheus metrics and Langfuse tracing
    ├── src/
    │   ├── document_reader.py  # Any supported file → text lines tagged with page (OCR or direct read)
    │   ├── sources.py          # Extraction → table rows with the source line of every value
    │   ├── common.py, pydantic_schema.py  # Invoice schema and validation
    │   ├── queues.py           # Queue topology (identical to the API's queues.py)
    │   ├── storage.py          # Downloads file_key from object storage, or decodes inline files
    │   └── errors.py, logger_config.py
    ├── k8s/                 # Deployment, KEDA / HPA autoscaling, secret template
    ├── scripts/smoke_test.py
    └── tests/

---

## 📜 License
This project is licensed under the **MIT License**.
