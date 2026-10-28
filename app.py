import json
import os
import re
import time
from contextlib import asynccontextmanager
from typing import List, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pika.exceptions import AMQPError
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

import broker
import metrics
import object_store
from job_store import JobStore

UPLOAD_FOLDER = "data"
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "25"))
MAX_FILES_PER_JOB = int(os.getenv("MAX_FILES_PER_JOB", "100"))
PROCESS_TIMEOUT = int(os.getenv("PROCESS_TIMEOUT", "600"))
MAX_COLUMNS = 50
MAX_COLUMN_CHARS = 100

# Must match src/document_reader.py on the worker branch: PDFs and images are OCR'd, the rest read as text.
SUPPORTED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp",
    ".txt", ".csv", ".tsv", ".md", ".json", ".xml", ".html", ".htm", ".docx",
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

store = JobStore(os.getenv("STORAGE_DIR", "storage"))


def on_result(result: dict) -> bool:
    """Store a worker result and record how long the job took once its last file is in."""
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


def submit_job(files: List[Tuple[str, bytes]], endpoint: str, columns: Optional[List[str]] = None) -> str:
    """Create a job and send one message per file to the workers, which process them in parallel."""
    columns = columns or []
    job_id = store.create([name for name, _ in files], columns)
    try:
        refs = object_store.file_refs(job_id, files)
    except object_store.StorageUnavailable as e:
        store.delete(job_id)
        raise HTTPException(status_code=503, detail=f"File storage unavailable: {e}")
    messages = [
        {"job_id": job_id, "filename": name, **ref, "columns": columns} for (name, _), ref in zip(files, refs)
    ]
    try:
        broker.publish_jobs(messages)
    except AMQPError as e:
        store.delete(job_id)
        object_store.delete(job_id, [ref["file_key"] for ref in refs if "file_key" in ref])
        metrics.PUBLISH_FAILURES.inc()
        raise HTTPException(status_code=503, detail=f"Job queue unavailable: {e!r}")
    metrics.JOBS_SUBMITTED.labels(endpoint).inc()
    metrics.PDFS_SUBMITTED.inc(len(files))
    return job_id


def read_files(uploads: List[UploadFile]) -> Tuple[List[Tuple[str, bytes]], List[str]]:
    """Supported uploads as (unique name, bytes), plus the names of the ones skipped."""
    files, skipped, seen = [], [], set()
    for upload in uploads:
        name = os.path.basename(upload.filename or "")
        stem, ext = os.path.splitext(name)
        if ext.lower() not in SUPPORTED_EXTENSIONS:
            skipped.append(name)
            continue
        data = upload.file.read()
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{name} is larger than {MAX_FILE_MB} MB")
        # Results are keyed by filename, so keep names unique within a job.
        n = 2
        while name in seen:
            name, n = f"{stem} ({n}){ext}", n + 1
        seen.add(name)
        files.append((name, data))
    return files, skipped


def parse_columns(raw: Optional[str]) -> List[str]:
    """Optional columns to extract: a JSON list, or names separated by commas or new lines."""
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = re.split(r"[,\n]", raw)
    if not isinstance(parsed, list) or not all(isinstance(c, str) for c in parsed):
        raise HTTPException(status_code=400, detail="columns must be a list of names")

    columns, seen = [], set()
    for c in (c.strip() for c in parsed):
        if c and c.lower() not in seen:
            seen.add(c.lower())
            columns.append(c)
    if len(columns) > MAX_COLUMNS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_COLUMNS} columns")
    if any(len(c) > MAX_COLUMN_CHARS for c in columns):
        raise HTTPException(status_code=400, detail=f"Column names are limited to {MAX_COLUMN_CHARS} characters")
    return columns


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
def create_job(
    files: List[UploadFile] = File(default=[]),
    pdfs: List[UploadFile] = File(default=[]),
    columns: Optional[str] = Form(default=None),
):
    """Queue documents for the workers and return immediately; poll GET /jobs/{job_id} for results.

    Every call gets its own job, so concurrent users never see each other's files. `columns`
    optionally names the fields to extract; without it the invoice schema is used. `pdfs` is
    the field name used before other file types were accepted.
    """
    uploads = files + pdfs
    if len(uploads) > MAX_FILES_PER_JOB:
        raise HTTPException(status_code=413, detail=f"At most {MAX_FILES_PER_JOB} files per job")
    wanted = parse_columns(columns)
    accepted, skipped = read_files(uploads)
    if not accepted:
        raise HTTPException(
            status_code=400, detail=f"No supported files in upload. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    job_id = submit_job(accepted, "jobs", wanted)
    return {
        "job_id": job_id,
        "status": "queued",
        "files": [name for name, _ in accepted],
        "skipped": skipped,
        "columns": wanted,
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    status = store.status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
