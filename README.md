# 📄 InvoiceAI Worker

The slow half of InvoiceAI: it takes PDFs off a RabbitMQ queue, runs **OCR (PaddleOCR) + LLM extraction (Gemini)**, validates the result against the invoice schema, and publishes it back. The API that accepts uploads and sends jobs here lives on the `fastapi` branch.

---

## ⚖️ How it scales

    fastapi (API) ──publish──> [invoice.jobs] ──> worker pod 1
                                              ──> worker pod 2      (one PDF per message)
                                              ──> worker pod N
    fastapi (API) <──consume── [invoice.results] <── every pod

- **Load balancing is done by RabbitMQ.** Every pod consumes from the same queue; each message goes to exactly one pod, and `prefetch=1` means a pod only takes a new PDF once it has finished the last. A bulk upload of 50 PDFs spreads across all available pods instead of queueing behind one.
- **No work is lost.** A message is acked only after its result is published. If a pod crashes or is scaled down mid-job, RabbitMQ hands the PDF to another pod.
- **Autoscaling** adds pods while the queue is backed up and removes them when it drains (`k8s/worker-keda.yaml`).

## Message format

Job (`invoice.jobs`), one per PDF:

    {"job_id": "…", "filename": "invoice.pdf", "pdf_b64": "<base64 PDF bytes>"}

Result (`invoice.results`):

    {"job_id": "…", "filename": "invoice.pdf", "ok": true,  "structured_data": {"extraction": [...]}}
    {"job_id": "…", "filename": "invoice.pdf", "ok": false, "error": "…"}

---

## 🚀 Run

Locally (needs a RabbitMQ and Python 3.10/3.11):

    pip install -r requirements.txt
    export RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
    export GOOGLE_API_KEY=your-gemini-key
    python worker.py

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
| `WORKER_PREFETCH` | 1 | PDFs a pod holds at once; keep 1 for even spreading |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used for extraction |
| `GOOGLE_API_KEY` | – | Gemini API key |

---

## 📈 Observability

Dashboards, alerts and log collection live on the `tracking` branch. This worker feeds them:

- **Prometheus metrics** on `:9100/metrics` (`METRICS_PORT`, `0` disables): PDFs processed by status, time per PDF and per stage (`ocr`, `llm`, `validate`), PDFs in progress, LLM calls, latency, tokens and estimated USD cost.
- **Langfuse** (set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`): one trace per PDF, grouped into a session per job, with spans for each stage and the Gemini generation including tokens, cost and latency.
- Cost is estimated from token usage at `LLM_INPUT_USD_PER_1M` / `LLM_OUTPUT_USD_PER_1M` (defaults: Gemini 2.5 Flash list price, $0.30 / $2.50); update them if pricing or the model changes.

---

## 🧪 Tests & CI/CD

Unit tests (OCR and LLM stubbed): `pip install -r requirements-dev.txt && pytest`.

Smoke test against a live broker and running worker: `python scripts/smoke_test.py`.

GitHub Actions (`.github/workflows/ci.yml`) on `worker`: unit tests → image build → worker container + real RabbitMQ round-trip → publish `ghcr.io/<owner>/<repo>-worker` (pushes only).

---

## 📂 Project Structure

    ├── worker.py            # RabbitMQ consumer
    ├── ocr_pipeline.py      # PDF → images → PaddleOCR → Gemini
    ├── src/                 # Pydantic schema, validation, logging
    ├── k8s/                 # Deployment, KEDA / HPA autoscaling, secret template
    ├── scripts/smoke_test.py
    └── tests/

---

## 📜 License
This project is licensed under the **MIT License**.
