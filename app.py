import base64
import os
import time
from contextlib import asynccontextmanager
from typing import List, Tuple

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pika.exceptions import AMQPError
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

import broker
import metrics
from job_store import JobStore

UPLOAD_FOLDER = "data"
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "25"))
MAX_FILES_PER_JOB = int(os.getenv("MAX_FILES_PER_JOB", "100"))
PROCESS_TIMEOUT = int(os.getenv("PROCESS_TIMEOUT", "600"))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

store = JobStore(os.getenv("STORAGE_DIR", "storage"))


def on_result(result: dict) -> bool:
    """Store a worker result and record how long the job took once its last PDF is in."""
    job_id = result.get("job_id")
    before = store.status(job_id)
    saved = store.save_result(result)
    if not saved:
        metrics.RESULTS.labels("unknown_job").inc()
        return False
    metrics.RESULTS.labels("ok" if result.get("ok") else "error").inc()
    if before and before["status"] != "done" and store.status(job_id)["status"] == "done":
        metrics.JOB_SECONDS.observe(time.time() - store.created_at(job_id))
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = None
    if os.getenv("RESULT_CONSUMER", "1") == "1":
        consumer = broker.ResultConsumer(lambda result: on_result(result))
        consumer.start()
    yield
    if consumer:
        consumer.stop()


app = FastAPI(
    title="InvoiceAI",
    description="Extract structured data from unstructured invoice PDFs. Processing runs on worker pods via RabbitMQ.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    # Label by route template (/jobs/{job_id}), not the raw path, to keep cardinality bounded.
    route = request.scope.get("route")
    path = route.path if route else "unmatched"
    metrics.REQUEST_SECONDS.labels(request.method, path).observe(time.perf_counter() - started)
    metrics.REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    return response


class DeleteRequest(BaseModel):
    filename: str


def safe_path(filename: str) -> str:
    """Keep client-supplied names inside the upload folder."""
    name = os.path.basename(filename or "")
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return os.path.join(UPLOAD_FOLDER, name)


def submit_job(files: List[Tuple[str, bytes]], endpoint: str) -> str:
    """Create a job and send one message per PDF to the workers."""
    job_id = store.create([name for name, _ in files])
    messages = [
        {"job_id": job_id, "filename": name, "pdf_b64": base64.b64encode(data).decode()} for name, data in files
    ]
    try:
        broker.publish_jobs(messages)
    except AMQPError as e:
        store.delete(job_id)
        metrics.PUBLISH_FAILURES.inc()
        raise HTTPException(status_code=503, detail=f"Job queue unavailable: {e!r}")
    metrics.JOBS_SUBMITTED.labels(endpoint).inc()
    metrics.PDFS_SUBMITTED.inc(len(files))
    return job_id


def read_pdfs(uploads: List[UploadFile]) -> List[Tuple[str, bytes]]:
    files, seen = [], set()
    for upload in uploads:
        name = os.path.basename(upload.filename or "")
        if not name.lower().endswith(".pdf"):
            continue
        data = upload.file.read()
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{name} is larger than {MAX_FILE_MB} MB")
        # Results are keyed by filename, so keep names unique within a job.
        stem, n = name[:-4], 2
        while name in seen:
            name, n = f"{stem} ({n}).pdf", n + 1
        seen.add(name)
        files.append((name, data))
    return files


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/upload")
def upload_files(pdfs: List[UploadFile] = File(...)):
    """Save uploaded PDFs into data/ folder"""
    saved_files = []

    for file in pdfs:
        save_path = safe_path(file.filename)
        with open(save_path, "wb") as f:
            f.write(file.file.read())
        saved_files.append(os.path.basename(save_path))

    return {"success": True, "uploaded": saved_files}


@app.post("/delete")
def delete_file(body: DeleteRequest):
    """Delete a PDF before processing if user cancels"""
    file_path = safe_path(body.filename)

    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"success": False, "error": "File not found"})

    os.remove(file_path)
    return {"success": True, "deleted": os.path.basename(file_path)}


@app.post("/process")
def process_files():
    """Send the uploaded PDFs to the workers and wait for their results (used by the web UI)."""
    names = sorted(f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(".pdf"))
    if not names:
        return {"success": False, "error": "No uploaded PDFs to process"}

    files = []
    for name in names:
        with open(os.path.join(UPLOAD_FOLDER, name), "rb") as f:
            files.append((name, f.read()))

    try:
        job_id = submit_job(files, "process")
    except HTTPException as e:
        return {"success": False, "error": e.detail}

    # Handed to the workers; clear them so the next /process doesn't resend them.
    for name in names:
        os.remove(os.path.join(UPLOAD_FOLDER, name))

    # Sync endpoint, so this wait runs in FastAPI's threadpool, not the event loop.
    deadline = time.time() + PROCESS_TIMEOUT
    while time.time() < deadline:
        status = store.status(job_id)
        if status["status"] == "done":
            return {"success": True, "job_id": job_id, "results": status["results"]}
        time.sleep(1)

    return {
        "success": False,
        "job_id": job_id,
        "error": f"Still processing after {PROCESS_TIMEOUT}s; check GET /jobs/{job_id}",
    }


@app.post("/jobs", status_code=202)
def create_job(pdfs: List[UploadFile] = File(...)):
    """Bulk entry point: queue PDFs for the workers and return immediately."""
    if len(pdfs) > MAX_FILES_PER_JOB:
        raise HTTPException(status_code=413, detail=f"At most {MAX_FILES_PER_JOB} files per job")
    files = read_pdfs(pdfs)
    if not files:
        raise HTTPException(status_code=400, detail="No PDF files in upload")

    job_id = submit_job(files, "jobs")
    return {"job_id": job_id, "status": "queued", "files": [name for name, _ in files]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    status = store.status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
