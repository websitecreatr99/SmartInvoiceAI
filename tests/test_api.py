import base64
import os

import pytest
from fastapi.testclient import TestClient
from pika.exceptions import AMQPConnectionError

import app as app_module
from job_store import JobStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    upload = tmp_path / "data"
    upload.mkdir()
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", str(upload))
    monkeypatch.setattr(app_module, "store", JobStore(str(tmp_path / "storage")))
    published = []
    monkeypatch.setattr(app_module.broker, "publish_jobs", lambda messages: published.extend(messages))
    # No `with` block, so the lifespan (and its RabbitMQ consumer) doesn't start.
    c = TestClient(app_module.app)
    c.published = published
    return c


def pdf(name, body=b"%PDF-1.4"):
    return ("pdfs", (name, body, "application/pdf"))


def worker_result(job_id, filename, ok=True):
    if ok:
        return {"job_id": job_id, "filename": filename, "ok": True, "structured_data": {"extraction": []}}
    return {"job_id": job_id, "filename": filename, "ok": False, "error": "OCR failed"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_and_delete(client):
    res = client.post("/upload", files=[pdf("a.pdf"), pdf("../b.pdf")])
    assert res.json() == {"success": True, "uploaded": ["a.pdf", "b.pdf"]}

    assert client.post("/delete", json={"filename": "a.pdf"}).json() == {"success": True, "deleted": "a.pdf"}
    res = client.post("/delete", json={"filename": "a.pdf"})
    assert res.status_code == 404
    assert res.json() == {"success": False, "error": "File not found"}


def test_create_job_publishes_one_message_per_pdf(client):
    res = client.post("/jobs", files=[pdf("a.pdf", b"AAA"), pdf("a.pdf", b"BBB"), pdf("notes.txt")])

    assert res.status_code == 202
    body = res.json()
    assert body["files"] == ["a.pdf", "a (2).pdf"]
    assert [(m["job_id"], m["filename"], base64.b64decode(m["pdf_b64"])) for m in client.published] == [
        (body["job_id"], "a.pdf", b"AAA"),
        (body["job_id"], "a (2).pdf", b"BBB"),
    ]


def test_create_job_validation(client, monkeypatch):
    assert client.post("/jobs", files=[("pdfs", ("x.txt", b"x", "text/plain"))]).status_code == 400
    monkeypatch.setattr(app_module, "MAX_FILES_PER_JOB", 1)
    assert client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf")]).status_code == 413
    monkeypatch.setattr(app_module, "MAX_FILE_MB", 0)
    assert client.post("/jobs", files=[pdf("a.pdf")]).status_code == 413
    assert client.published == []


def test_queue_down_returns_503_and_drops_job(client, monkeypatch, tmp_path):
    def down(messages):
        raise AMQPConnectionError("refused")

    monkeypatch.setattr(app_module.broker, "publish_jobs", down)

    res = client.post("/jobs", files=[pdf("a.pdf")])

    assert res.status_code == 503
    assert not os.listdir(tmp_path / "storage" / "jobs")


def test_job_status_lifecycle(client):
    job_id = client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf")]).json()["job_id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"

    app_module.store.save_result(worker_result(job_id, "a.pdf"))
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "processing"
    assert body["progress"] == {"done": 1, "total": 2}

    app_module.store.save_result(worker_result(job_id, "b.pdf", ok=False))
    body = client.get(f"/jobs/{job_id}").json()
    assert body["status"] == "done"
    assert body["results"] == [
        {"filename": "a.json", "structured_data": {"extraction": []}},
        {"filename": "b.json", "error": "OCR failed"},
    ]


def test_unknown_job(client):
    assert client.get("/jobs/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/jobs/not-a-uuid").status_code == 404
    assert app_module.store.save_result(worker_result("00000000-0000-0000-0000-000000000000", "a.pdf")) is False
    assert app_module.store.save_result(worker_result("../../etc", "a.pdf")) is False


def test_process_waits_for_worker_results(client, monkeypatch):
    # Simulate workers answering as soon as the messages are published.
    def publish_and_answer(messages):
        for m in messages:
            app_module.store.save_result(worker_result(m["job_id"], m["filename"]))

    monkeypatch.setattr(app_module.broker, "publish_jobs", publish_and_answer)
    client.post("/upload", files=[pdf("a.pdf"), pdf("b.pdf")])

    body = client.post("/process").json()

    assert body["success"] is True
    assert [r["filename"] for r in body["results"]] == ["a.json", "b.json"]
    assert os.listdir(app_module.UPLOAD_FOLDER) == []


def test_process_times_out_with_job_id(client, monkeypatch):
    monkeypatch.setattr(app_module, "PROCESS_TIMEOUT", 0)
    client.post("/upload", files=[pdf("a.pdf")])

    body = client.post("/process").json()

    assert body["success"] is False
    assert body["job_id"] in body["error"]


def test_process_with_nothing_uploaded(client):
    assert client.post("/process").json() == {"success": False, "error": "No uploaded PDFs to process"}
