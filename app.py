import json
import os
import socket
import uuid
from typing import List

from celery.result import AsyncResult
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from celery_app import celery_app
from jobs import input_dir, job_dir, results_dir

MAX_FILES_PER_JOB = int(os.getenv("MAX_FILES_PER_JOB", "20"))
HOSTNAME = socket.gethostname()

app = FastAPI(title="InvoiceAI", description="Extract structured data from unstructured invoice PDFs.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Served-By"],
)


@app.middleware("http")
async def served_by(request: Request, call_next):
    """Tag responses with the replica that handled them, to make load balancing visible."""
    response = await call_next(request)
    response.headers["X-Served-By"] = HOSTNAME
    return response


def check_job_id(job_id: str) -> str:
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")
    if not os.path.isdir(job_dir(job_id)):
        raise HTTPException(status_code=404, detail="Job not found")
    return job_id


def read_results(job_id: str) -> list:
    """Same per-file shape the old /process endpoint returned."""
    folder = results_dir(job_id)
    if not os.path.isdir(folder):
        return []
    results = []
    for filename in sorted(os.listdir(folder)):
        path = os.path.join(folder, filename)
        name, ext = os.path.splitext(filename)
        with open(path, "r", encoding="utf-8") as f:
            if ext == ".json":
                results.append({"filename": filename, "structured_data": json.load(f)})
            elif ext == ".error":
                results.append({"filename": f"{name}.json", "error": f.read()})
    return results


@app.get("/health")
def health():
    return {"status": "ok", "served_by": HOSTNAME}


@app.post("/jobs", status_code=202)
def create_job(pdfs: List[UploadFile] = File(...)):
    """Store the PDFs under a new job and queue it for the workers."""
    if len(pdfs) > MAX_FILES_PER_JOB:
        raise HTTPException(status_code=413, detail=f"At most {MAX_FILES_PER_JOB} files per job")

    job_id = str(uuid.uuid4())
    os.makedirs(input_dir(job_id))

    saved = []
    for file in pdfs:
        name = os.path.basename(file.filename or "")
        if not name.lower().endswith(".pdf"):
            continue
        with open(os.path.join(input_dir(job_id), name), "wb") as f:
            f.write(file.file.read())
        saved.append(name)

    if not saved:
        raise HTTPException(status_code=400, detail="No PDF files in upload")

    # The task id doubles as the job id so status can be looked up directly.
    celery_app.send_task("tasks.process_job", args=[job_id], task_id=job_id)
    return {"job_id": job_id, "status": "queued", "files": saved}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    check_job_id(job_id)
    result = AsyncResult(job_id, app=celery_app)
    state = result.state
    info = result.info if isinstance(result.info, dict) else {}
    total = len(os.listdir(input_dir(job_id)))

    if state == "SUCCESS":
        return {"job_id": job_id, "status": "done", "progress": {"done": total, "total": total}, "results": read_results(job_id)}
    if state == "FAILURE":
        return {"job_id": job_id, "status": "failed", "error": str(result.info)}
    if state in ("STARTED", "PROGRESS", "RETRY"):
        return {
            "job_id": job_id,
            "status": "processing",
            "progress": {"done": info.get("done", 0), "total": total, "current": info.get("current")},
        }
    return {"job_id": job_id, "status": "queued", "progress": {"done": 0, "total": total}}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
