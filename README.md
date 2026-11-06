# 📄 InvoiceAI API

InvoiceAI extracts **structured data** from **unstructured business documents** (invoices, purchase orders and similar) using **OCR + an LLM (Gemini)**. Either it fills the invoice schema (header + line items), or it pulls just the columns you name. Every value cites the document line it came from.

This is the **`lite` branch**: the `fastapi` branch's API plus a copy of the worker that runs inside the API process, so the whole backend is one small service with no RabbitMQ. It is what runs the free live deployment (see [Single free service](#-single-free-service-lite-branch)). The other parts of the system live on their own branches:

| Branch | What |
|--------|------|
| `fastapi` | HTTP API: accepts uploads, queues work, collects results |
| `lite` (this one) | `fastapi` + the worker in one process, no RabbitMQ: the free deployment on Render |
| `worker` | OCR + LLM extraction pods that consume the queue (PaddleOCR, or Gemini with `OCR_ENGINE=gemini`) |
| `frontend` | Next.js web UI (talks to this API through `/api/*`), deployed on Vercel |
| `tracking` | Prometheus, Loki, Grafana and Langfuse |
| `infra` | Terraform for AWS (ECS Fargate, Amazon MQ, EFS), plus Hugging Face and Oracle bundles |

**Live:** frontend https://hackathon-frontend-gamma-seven.vercel.app, backend https://hackathon-elnx.onrender.com (`/health`, `/docs`). The backend sleeps when idle, so the first request can take up to a minute.

To run your own copy online for free, see [Deploy your own copy for free](#deploy-your-own-copy-for-free-render--vercel). To run it on your machine, see [Getting Started](#-getting-started).

---

## Deploy your own copy for free (Render + Vercel)

This puts the whole system online at no cost and needs no credit card:
- **Backend on Render:** the `lite` branch. It is the API and the worker in one service, with Gemini reading the documents, so there is no RabbitMQ and no PaddleOCR. It uses about 110 MB of RAM.
- **Frontend on Vercel:** the `frontend` branch.

The browser only ever talks to Vercel, which forwards `/api/*` to Render.

    Browser ──► Vercel (frontend branch) ──/api/*──► Render (lite branch: API + worker) ──► Gemini API

It takes about 20 minutes. The Render build takes 5–10 of those.

### What you need

| Account / tool | Used for | Card needed? |
|---|---|---|
| GitHub account | Render and Vercel deploy from your own copy of the repo | No |
| [Google AI Studio](https://aistudio.google.com/apikey) API key | Gemini: reads the documents and extracts the data | No (free tier) |
| [Render](https://render.com) account (sign in with GitHub) | Backend | No (free web service) |
| [Vercel](https://vercel.com) account (sign in with GitHub) | Frontend | No (Hobby plan) |
| Git, and Node.js 20+ for the Vercel CLI | Copying the repo, deploying the frontend | – |
| [UptimeRobot](https://uptimerobot.com) account (optional) | Keeping the free backend awake | No |

### Step 1: Put a copy of the repo in your GitHub account

Render and Vercel can only deploy repositories your GitHub account can see.

1. On GitHub, create an **empty** repository: no README, no .gitignore, no license. In these steps it's called `invoiceai`.
2. Copy every branch into it:

       git clone --bare https://github.com/kishannextq/hackathon.git
       cd hackathon.git
       git push --mirror https://github.com/<your-user>/invoiceai.git
       cd .. && rm -rf hackathon.git

3. Optionally, in your repo's **Settings → General → Default branch**, choose `fastapi`.

If you were added to this repository, a fork also works: **Fork**, with "Copy the main branch only" **unchecked**, so you get `lite` and `frontend`.

### Step 2: Create a Gemini API key

1. Open https://aistudio.google.com/apikey and choose **Create API key**. **Create API key in new project** gives the key its own free quota.
2. Copy the key; you'll paste it into Render in the next step.

The service uses two models: `gemini-3.5-flash-lite` for extraction and `gemini-3.1-flash-lite` for reading the document. Each has its own free daily quota. Every document costs one request of each.
- Gemini 2.5 models are closed to new keys, so don't switch to them.
- `gemini-3.5-flash` extracts a bit better, but its free tier allowed only 20 requests a day.

### Step 3: Deploy the backend on Render

1. Sign in to https://dashboard.render.com with GitHub.
2. When asked, let Render's GitHub app access your `invoiceai` repo. You can change this later under **Account settings → Git providers**.
3. Create the service. Use the Blueprint if your account has it; otherwise set it up by hand.

   **A. Blueprint (if your dashboard has New → Blueprint):** choose **New → Blueprint**, then your repo and branch **`lite`**. Render reads `render.yaml` and asks for `GOOGLE_API_KEY`. Paste the key, then click **Apply**.

   **B. By hand (if there's no Blueprint option):** choose **New → Web Service**, pick your repo, and fill in:

   | Field | Value |
   |---|---|
   | Branch | `lite` |
   | Language / Runtime | `Docker` |
   | Dockerfile Path | `./Dockerfile.lite` |
   | Docker Build Context | `.` |
   | Instance Type | **Free** |
   | Health Check Path (under Advanced) | `/health` |
   | Auto-Deploy | On commit |

   Then add these **Environment Variables**:

   | Key | Value |
   |---|---|
   | `GOOGLE_API_KEY` | your Gemini key |
   | `GEMINI_MODEL` | `gemini-3.5-flash-lite` |
   | `GEMINI_OCR_MODEL` | `gemini-3.1-flash-lite` |
   | `MAX_FILE_MB` | `15` |
   | `MAX_FILES_PER_JOB` | `20` |

   Click **Deploy Web Service**. Don't set `PORT`: Render provides it, and the image listens on it.

4. Wait for the deploy to show **Live**: 5–10 minutes the first time. Copy the service URL, for example `https://invoiceai-api-xxxx.onrender.com`.
5. Check it:

       curl https://<your-service>.onrender.com/health      # {"status":"ok"}

   The interactive API docs are at `https://<your-service>.onrender.com/docs`.

### Step 4: Deploy the frontend on Vercel

The frontend forwards `/api/*` to your Render URL. That URL is read **at build time** from `BACKEND_URL`, so set it before or during the build. If you change it later, you must redeploy.

**Option A: Vercel CLI (what the live demo uses)**

    git clone -b frontend https://github.com/<your-user>/invoiceai.git invoiceai-frontend
    cd invoiceai-frontend
    npx vercel login
    npx vercel link             # answer "N" to linking an existing project; it creates a new one
    npx vercel deploy --prod --build-env BACKEND_URL=https://<your-service>.onrender.com

The last command prints the site's URL, for example `https://invoiceai-frontend-xxxx.vercel.app`.

This project isn't connected to Git, so pushing to `frontend` doesn't redeploy it. Run the `deploy` command again whenever you want an update.

**Option B: Vercel dashboard (redeploys on every push to `frontend`)**

1. Go to https://vercel.com/new and **Import** your `invoiceai` repo. Framework: **Next.js**. Root Directory: `./`.
2. Under **Environment Variables**, add `BACKEND_URL` = `https://<your-service>.onrender.com`, then **Deploy**.
   - This first build uses the repo's default branch. If that isn't `frontend`, it fails or builds the wrong code; that's expected.
3. In **Project → Settings → Git → Production Branch**, set **`frontend`**.
4. Under **Deployments**, find a deployment of `frontend`. If there isn't one yet, push any commit to `frontend`. Then choose **Redeploy**.

Next.js is pinned to 15.5.29 on `frontend`. Vercel refuses to build the vulnerable 15.5.4, so don't downgrade it.

### Step 5: Allow your site in the backend's CORS list (optional)

The browser calls Vercel, and Vercel calls Render server-side, so CORS isn't needed for the normal setup.
- **Blueprint users:** `render.yaml` sets `CORS_ORIGINS` to this project's own demo URL. Replace it with your Vercel URL in **Render → your service → Environment**.
- **Only if** you build the frontend with `NEXT_PUBLIC_API_URL`, so the browser calls Render directly, CORS is required: set `CORS_ORIGINS` to your Vercel URL there.

### Step 6: Keep the backend awake (recommended)

Render's free services go to sleep after 15 minutes without requests, and the next request then waits 30–60 s while the service starts. To prevent this, use a free monitor:
1. At https://uptimerobot.com, choose **Add New Monitor**: type **HTTP(s)**, URL `https://<your-service>.onrender.com/health`, interval **5 minutes**.
2. A single always-on service fits inside Render's 750 free instance-hours a month.

### Step 7: Test it end to end

**In the browser:**
1. Open your Vercel URL.
2. Drop in the sample PDFs from `data/` on this branch, and click run. Optionally, first add columns such as `PO number`, `Quantity`, `Date ordered`.
   - **Without an API key** in the UI's **Gemini API key** field, you get **sample (dummy) data** straight away, with a notice saying so. Nothing is read from the files and no Gemini quota is used.
   - **With your key** pasted there, the documents are really read. The key is sent only with that upload and is never stored on the server. "Remember on this device" keeps it in this browser only.
   - The server's own `GOOGLE_API_KEY` is used for keyless visitors only if you set `DEMO_WITHOUT_KEY=0` on Render.
3. The Table, Visual and JSON views fill in as each file finishes. Every value links to the document line it was read from.

**From a terminal** (this goes through Vercel, like the browser does):

    SITE=https://<your-site>.vercel.app
    curl $SITE/api/health                                                        # {"status":"ok"}
    curl -F "files=@data/99907349 Roof 3-redacted.pdf" $SITE/api/jobs            # {"job_id":"…","status":"queued",…}
    curl $SITE/api/jobs/<job_id>                                                 # repeat until "status":"done"

For custom columns, add `-F 'columns=["PO number","Quantity","Date ordered"]'` to the `POST`.

A document usually takes 10–40 s. The first request after the service has been asleep takes longer.

### Updating your deployment

| You changed | What to do |
|---|---|
| Backend code | Push to `lite`; Render redeploys by itself. Worker code is a copy: change it on `worker`, then run `scripts/sync_worker.sh` on `lite` and push |
| Frontend code | **CLI setup:** run the `npx vercel deploy --prod --build-env BACKEND_URL=…` command again. **Dashboard setup:** push to `frontend` |
| Render URL | Redeploy the frontend: `BACKEND_URL` is compiled into the build |
| Gemini key | Render → your service → **Environment** → edit `GOOGLE_API_KEY` → Save (it redeploys) |

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Render build: `open Dockerfile.lite: no such file or directory` | The service is building the wrong branch. Set the branch to **`lite`** in Render → Settings → Build & Deploy |
| Render shows no **Blueprint** option, or doesn't list your repo | Use the **By hand** setup in Step 3, and give Render's GitHub app access to your repo (Account settings → Git providers) |
| The first request hangs for about a minute, then works | The free service was asleep. Add the UptimeRobot monitor (Step 6) |
| A file fails with a 404 `models/... is not found` | The model name is wrong or closed to your key. Use the two Flash-Lite models above |
| Files fail with `429` / `RESOURCE_EXHAUSTED` | The free daily Gemini quota is used up. Wait for the daily reset, use a key in another project, or enable billing on the Google project |
| An occasional `Validation Error` in one file's result | Flash-Lite sometimes returns malformed output. The service already retries once; re-run that file |
| The site loads, but every upload says `Upload failed` | `BACKEND_URL` was missing or wrong at build time. Redeploy the frontend with the right Render URL |
| Vercel build is blocked as vulnerable | Next.js was downgraded. Keep `next` at 15.5.29 or newer on `frontend` |

Limits of the free setup:
- One document is processed at a time.
- Jobs and results are kept on the service's temporary disk, so they are lost when it restarts, sleeps or redeploys.
- Throughput is capped by Gemini's free quota.

For the scalable version, see Architecture below: RabbitMQ, separate PaddleOCR workers that autoscale, and monitoring. To run that on AWS, see the `infra` branch.

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
| `INLINE_WORKER` | 0 | `1` processes jobs inside the API process (see below) instead of via RabbitMQ |
| `DEMO_WITHOUT_KEY` | 1 | Jobs sent without the caller's own Gemini key (`X-Gemini-Api-Key` header, the UI's API key field) get sample data at once (`demo.py`, marked `"demo": true`) instead of using the workers' `GOOGLE_API_KEY`. `0` processes them with the workers' key; `docker-compose.yml` and `k8s/` set `0` |

### 🆓 Single free service (`lite` branch)

`Dockerfile.lite` runs everything as one small service: the API plus the worker's pipeline in-process (`INLINE_WORKER=1`, `inline_worker.py`), with Gemini transcribing documents instead of PaddleOCR (`OCR_ENGINE=gemini`). No RabbitMQ, about 110 MB of RAM, so it fits Render's free web service.

1. Render → **New → Blueprint** → this repo, branch `lite`. `render.yaml` defines the service; enter `GOOGLE_API_KEY` when asked. If your account has no Blueprint option, create a **Web Service** instead: runtime Docker, branch `lite`, Dockerfile path `./Dockerfile.lite`, health check `/health`, instance type Free, and the environment variables listed in `render.yaml`.
2. Free services sleep after 15 minutes without requests: add a free UptimeRobot HTTP monitor on `https://<service>.onrender.com/health` every 5 minutes.
3. Point the frontend at it: deploy the `frontend` branch to Vercel with `BACKEND_URL=https://<service>.onrender.com` (a build-time variable; see that branch's README), and put the Vercel URL in `CORS_ORIGINS`.

The live service redeploys automatically on every push to `lite`. It uses `GEMINI_MODEL=gemini-3.5-flash-lite` for extraction and `GEMINI_OCR_MODEL=gemini-3.1-flash-lite` for OCR (Gemini 2.5 models are closed to new API keys). Flash-Lite occasionally returns output that fails validation, so the in-process worker retries such a document once.

`worker/` is a copy of the worker branch's pipeline: refresh it with `scripts/sync_worker.sh`. Trade-offs against the RabbitMQ setup: one document at a time, no redelivery if the process restarts mid-job, job history is lost on restart, and Gemini's free tier caps the documents per day (each document is two requests; `GEMINI_OCR_MODEL` and `GEMINI_MODEL` use separate quotas).

### ☸️ Kubernetes

    cp k8s/secret.example.yaml k8s/secret.yaml   # fill in values
    kubectl apply -f k8s/secret.yaml -f k8s/rabbitmq.yaml -f k8s/api.yaml

Worker Deployment and autoscaling manifests are on the `worker` branch (`k8s/`). For AWS ECS, see the `infra` branch.

**Upgrading a deployment from before the quorum queue.** RabbitMQ can't change an existing queue's type, and old and new services can't share `invoice.jobs`. Scale the workers to 0, run `RABBITMQ_URL=... python scripts/migrate_queues.py` (it parks queued jobs, recreates the queues and moves the jobs back; safe to re-run), then deploy the new API and worker images. New jobs get a 503 between the migration and the new API rollout.

### 🧪 Tests & CI/CD

`pip install -r requirements-dev.txt && pytest` runs the unit tests. With `RABBITMQ_URL` set it also runs 3 integration tests that push a 12-PDF job through a real broker to three fake workers and check the load is shared (they are skipped otherwise).

`scripts/fake_worker.py` speaks the worker's queue protocol without OCR or an LLM, which is handy for testing the API against a real RabbitMQ: `RABBITMQ_URL=... python scripts/fake_worker.py`.

GitHub Actions (`.github/workflows/ci.yml`) on `fastapi`: unit + RabbitMQ integration tests → image build → container smoke test through RabbitMQ (`scripts/smoke_test.sh`) → publish `ghcr.io/<owner>/<repo>-api` (pushes only). Once the `infra` branch's Terraform is applied and the repository variable `AWS_DEPLOY_ROLE_ARN` is set (its `github_deploy_role_arn` output), pushes also build the image into ECR and roll it out to ECS (`deploy-aws` job; optional variables `AWS_REGION`, `ECS_CLUSTER`). Without that variable the job is skipped.

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
    ├── inline_worker.py    # INLINE_WORKER=1: runs the worker pipeline in-process, with retries
    ├── worker/             # Copy of the worker branch's pipeline (scripts/sync_worker.sh)
    ├── Dockerfile.lite     # Single free service: API + in-process worker, Gemini OCR
    ├── render.yaml         # Render Blueprint for Dockerfile.lite
    ├── docker-compose.yml  # RabbitMQ + API + worker pods
    ├── k8s/                # RabbitMQ, API, secret template
    ├── scripts/            # Container smoke test, fake worker for tests, queue migration, sync_worker.sh
    ├── tests/              # Unit, metrics and RabbitMQ integration tests
    ├── data/               # Sample documents for trying the API
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
