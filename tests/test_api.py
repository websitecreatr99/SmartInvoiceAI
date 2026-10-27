import json
import os
import sys
import types
import uuid

import pytest
from fastapi.testclient import TestClient

import app as app_module
import jobs


class FakeResult:
    def __init__(self, state="PENDING", info=None):
        self.state = state
        self.info = info


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "STORAGE_DIR", str(tmp_path))
    sent = []
    monkeypatch.setattr(app_module.celery_app, "send_task", lambda name, args, task_id: sent.append((name, args, task_id)))
    c = TestClient(app_module.app)
    c.sent = sent
    return c


def set_state(monkeypatch, state, info=None):
    monkeypatch.setattr(app_module, "AsyncResult", lambda job_id, app: FakeResult(state, info))


def pdf(name, body=b"%PDF-1.4"):
    return ("pdfs", (name, body, "application/pdf"))


def test_health_reports_replica(client):
    res = client.get("/health")
    assert res.json()["status"] == "ok"
    assert res.headers["X-Served-By"] == app_module.HOSTNAME


def test_create_job_stores_files_and_enqueues(client):
    res = client.post("/jobs", files=[pdf("a.pdf"), pdf("../b.pdf"), pdf("notes.txt")])

    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "queued"
    assert body["files"] == ["a.pdf", "b.pdf"]
    assert sorted(os.listdir(jobs.input_dir(body["job_id"]))) == ["a.pdf", "b.pdf"]
    assert client.sent == [("tasks.process_job", [body["job_id"]], body["job_id"])]


def test_create_job_rejects_upload_without_pdfs(client):
    res = client.post("/jobs", files=[("pdfs", ("notes.txt", b"x", "text/plain"))])
    assert res.status_code == 400
    assert client.sent == []


def test_create_job_limits_file_count(client, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_FILES_PER_JOB", 1)
    assert client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf")]).status_code == 413


def test_unknown_job_is_404(client):
    assert client.get(f"/jobs/{uuid.uuid4()}").status_code == 404
    assert client.get("/jobs/..%2F..%2Fetc").status_code == 404


def test_job_status_lifecycle(client, monkeypatch):
    job_id = client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf")]).json()["job_id"]

    set_state(monkeypatch, "PENDING")
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"

    set_state(monkeypatch, "PROGRESS", {"done": 1, "total": 2, "current": "b.pdf"})
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "processing"
    assert body["progress"] == {"done": 1, "total": 2, "current": "b.pdf"}

    os.makedirs(jobs.results_dir(job_id))
    doc = {"extraction": []}
    with open(os.path.join(jobs.results_dir(job_id), "a.json"), "w") as f:
        json.dump(doc, f)
    with open(os.path.join(jobs.results_dir(job_id), "b.error"), "w") as f:
        f.write("OCR failed")

    set_state(monkeypatch, "SUCCESS")
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["results"] == [
        {"filename": "a.json", "structured_data": doc},
        {"filename": "b.json", "error": "OCR failed"},
    ]

    set_state(monkeypatch, "FAILURE", RuntimeError("worker crashed"))
    assert client.get(f"/jobs/{job_id}").json() == {"job_id": job_id, "status": "failed", "error": "worker crashed"}


def test_worker_task_writes_results_and_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "STORAGE_DIR", str(tmp_path))
    job_id = str(uuid.uuid4())
    os.makedirs(jobs.input_dir(job_id))
    for name in ("good.pdf", "bad.pdf"):
        open(os.path.join(jobs.input_dir(job_id), name), "wb").close()

    def extract_text_from_pdf(path, out):
        if "bad" in path:
            raise RuntimeError("unreadable PDF")
        return [("INVOICE 42", 0.99)]

    class ModelHandler:
        def __init__(self, model):
            pass

        def extract_with_gemini(self, ocr_text):
            assert "INVOICE 42" in ocr_text
            return {"extraction": [{"header": {"job_number": "42"}, "line_items": []}]}

    # Stand-in for the real pipeline so the test needs no OCR/LLM dependencies.
    monkeypatch.setitem(
        sys.modules,
        "ocr_pipeline",
        types.SimpleNamespace(extract_text_from_pdf=extract_text_from_pdf, ModelHandler=ModelHandler),
    )
    import tasks

    monkeypatch.setattr(tasks.process_job, "update_state", lambda **kw: None)

    summary = tasks.process_job.run(job_id)

    assert summary["total"] == 2
    assert {f["filename"]: f["ok"] for f in summary["files"]} == {"bad.json": False, "good.json": True}
    with open(os.path.join(jobs.results_dir(job_id), "good.json")) as f:
        assert json.load(f)["extraction"][0]["header"]["job_number"] == "42"
    with open(os.path.join(jobs.results_dir(job_id), "bad.error")) as f:
        assert "unreadable PDF" in f.read()
