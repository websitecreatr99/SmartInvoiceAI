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
Create a `.env` file in the project root and add your **Gemini API Key** (read by the worker pods):
GEMINI_API_KEY=your_api_key_here

text
🔑 You can get a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

### 4️⃣ Run everything

docker compose up -d --build

This starts RabbitMQ, the API on port 5000, and two worker pods (image from the `worker` branch). Add workers with `docker compose up -d --scale worker=4`. RabbitMQ's dashboard is at http://localhost:15672 (guest/guest).

To run just the API locally: `RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F python app.py`.

---

## ⚖️ Architecture

This branch is the **API**. The slow work (OCR + LLM extraction) runs on the `worker` branch's pods:

    client ──> API ──publish──> RabbitMQ [invoice.jobs] ──> worker pod 1..N  (OCR + Gemini)
                 ^                                               │
                 └──consume── RabbitMQ [invoice.results] <───────┘

- Every PDF becomes one message, so a bulk upload fans out across all worker pods; RabbitMQ gives each pod one PDF at a time.
- Messages are durable and only acknowledged after processing, so a crashed pod's PDF is retried by another.
- The API stays fast and light: it never runs OCR, and its image has no ML dependencies.
- Job state lives in `STORAGE_DIR`. Running several API replicas requires that directory on shared (ReadWriteMany) storage.

### ☸️ Kubernetes

    cp k8s/secret.example.yaml k8s/secret.yaml   # fill in values
    kubectl apply -f k8s/secret.yaml -f k8s/rabbitmq.yaml -f k8s/api.yaml

Worker Deployment and autoscaling manifests are on the `worker` branch (`k8s/`).

### 🧪 Tests & CI/CD

`pip install -r requirements-dev.txt && pytest` runs the unit tests. With `RABBITMQ_URL` set it also runs integration tests that push a 12-PDF job through a real broker to three fake workers and check the load is shared.

GitHub Actions (`.github/workflows/ci.yml`) on `fastapi`: unit + RabbitMQ integration tests → image build → container smoke test through RabbitMQ → publish `ghcr.io/<owner>/<repo>-api` (pushes only).

---

## 🖥️ Usage
Interactive API docs are at [http://127.0.0.1:5000/docs](http://127.0.0.1:5000/docs).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/upload` | Save PDFs (multipart field `pdfs`) into `data/` |
| POST | `/delete` | Remove an uploaded PDF (`{"filename": "..."}`) |
| POST | `/process` | Send uploaded PDFs to the workers and wait for the results (used by the web UI) |
| POST | `/jobs` | **Bulk:** queue PDFs and return `202` with a `job_id` immediately |
| GET | `/jobs/{job_id}` | `queued` → `processing` (with progress) → `done` with results |
| GET | `/health` | Liveness check |

---

## 📸 Preview Screenshot
<p align="center">
  <img src="assets/Screenshot 2025-08-28 125448.png" alt="InvoiceAI Preview" width="700">
</p>

---

## 📂 Project Structure
.
├── app.py # FastAPI app
├── broker.py # RabbitMQ publisher + result consumer
├── job_store.py # Job state and results on disk
├── docker-compose.yml # RabbitMQ + API + worker pods
├── k8s/ # RabbitMQ, API, secret template
├── scripts/ # Container smoke test, fake worker for tests
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

