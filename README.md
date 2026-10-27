# 📄 Invoice Extractor from Unstructured PDF Data

## InvoiceAI (PDF → Unstructured Data Extractor)

InvoiceAI is a lightweight tool that extracts **structured data** (headers, line items, schema) from **unstructured PDFs** using **OCR + AI**.  
It’s designed for **invoices, purchase orders, and other business documents** where accuracy and structure matter.

---

## 🚀 Getting Started

Follow these steps to set up and run the project locally.

### 1️⃣ Clone the Repository

git clone https://github.com/websitecreatr99/InvoiceAI.git
cd InvoiceAI

text

### 2️⃣ Install Dependencies
Make sure you have **Python 3.9+** installed. Then run:
pip install -r requirements.txt

text

### 3️⃣ Create Environment Variables
Create a `.env` file in the project root and add your **Gemini API Key**:
GEMINI_API_KEY=your_api_key_here

text
🔑 You can get a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

### 4️⃣ Run the stack

docker compose up -d --build

The app is served through nginx at [http://localhost:8080](http://localhost:8080) (API docs at `/docs`).

---

## ⚖️ Architecture: scaling to many users

OCR and LLM extraction take seconds to minutes per PDF, so they never run inside a web request:

    client ──> nginx (load balancer) ──> API replicas ──> Redis queue ──> Celery workers
                                              │                              │
                                              └──── shared storage volume ───┘

- **API** (`app.py`) is stateless: it saves uploads under `storage/jobs/<job_id>/`, queues the job and returns at once. Any replica can answer any request, and each response carries an `X-Served-By` header naming the replica.
- **Workers** (`tasks.py`) run PDF → images → PaddleOCR → Gemini → validation. Each takes one job at a time, and a job is re-queued if its worker dies.
- **Each job is isolated** in its own folder, so concurrent users never see each other's files.

Scale each tier independently:

    docker compose up -d --scale api=3 --scale worker=6

| Setting | Default | Meaning |
|---------|---------|---------|
| `API_REPLICAS` / `--scale api=N` | 2 | API containers behind nginx |
| `UVICORN_WORKERS` | 2 | Processes per API container |
| `WORKER_REPLICAS` / `--scale worker=N` | 2 | Worker containers |
| `WORKER_CONCURRENCY` | 1 | Jobs per worker container (OCR is CPU/RAM heavy) |
| `MAX_FILES_PER_JOB` | 20 | Upload limit per job |
| `JOB_TIME_LIMIT` | 1800 | Seconds before a job is killed |

Put `GEMINI_API_KEY` in `.env`; workers load it automatically.

### 🧪 Tests & CI/CD

Unit tests: `pip install -r requirements-dev.txt && pytest`.
Full-stack smoke test (nginx, 2 API replicas, Redis, 2 workers): `bash scripts/smoke_test.sh`.

GitHub Actions (`.github/workflows/ci.yml`) runs on pushes and pull requests to `fastapi`, `worker` and `main`: unit tests → Docker build → full-stack smoke test → publish to `ghcr.io/<owner>/<repo>-api` (pushes only).

---

## 🖥️ Usage

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/jobs` | Upload PDFs (multipart field `pdfs`); returns `202` with a `job_id` |
| GET | `/jobs/{job_id}` | `queued` → `processing` (with progress) → `done` (with results) or `failed` |
| GET | `/health` | Liveness check |

Results use the same per-file shape as the old `/process` endpoint: `{"filename", "structured_data"}` or `{"filename", "error"}`.

---

## 📸 Preview Screenshot
<p align="center">
  <img src="assets/Screenshot 2025-08-28 125448.png" alt="InvoiceAI Preview" width="700">
</p>

---

## 📂 Project Structure
.
├── app.py # FastAPI API (enqueues jobs)
├── tasks.py # Celery worker task (OCR + LLM)
├── celery_app.py # Celery / Redis config
├── docker-compose.yml # nginx, API, Redis, workers
├── nginx.conf # Load balancer
├── ocr_pipeline.py # OCR + extraction pipeline
├── src/ # Pydantic schema, validation, logging
├── structured_output/ # Extracted JSON results
├── requirements.txt # Dependencies
└── .env # Your Gemini API key

text

---

## ✅ Features
- 📂 Upload multiple PDFs  
- ❌ Remove unwanted files before processing  
- 🧾 Extract structured JSON (headers, line items, schema)  
- 🎨 Simple, modern UI  

---

## 📜 License
This project is licensed under the **MIT License**.  
Free to use and modify.

---

