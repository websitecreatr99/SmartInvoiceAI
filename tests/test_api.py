import base64
import os

import pytest
from fastapi.testclient import TestClient
from botocore.exceptions import EndpointConnectionError
from pika.exceptions import AMQPConnectionError

import app as app_module
import object_store
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


FIELDS = {"columns": ["PO number"], "rows": [{"PO number": {"value": "1", "source": {"page": 1, "line": 3, "text": "PO 1", "confidence": 0.9}}}]}


def worker_result(job_id, filename, ok=True):
    if ok:
        return {"job_id": job_id, "filename": filename, "ok": True, "structured_data": {"extraction": []}, "fields": FIELDS}
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


def upload(name, body=b"x"):
    return ("files", (name, body, "application/octet-stream"))


def test_create_job_publishes_one_message_per_pdf(client):
    res = client.post("/jobs", files=[pdf("a.pdf", b"AAA"), pdf("a.pdf", b"BBB"), pdf("setup.exe")])

    assert res.status_code == 202
    body = res.json()
    assert body["files"] == ["a.pdf", "a (2).pdf"]
    assert body["skipped"] == ["setup.exe"]
    assert [(m["job_id"], m["filename"], base64.b64decode(m["file_b64"]), m["columns"]) for m in client.published] == [
        (body["job_id"], "a.pdf", b"AAA", []),
        (body["job_id"], "a (2).pdf", b"BBB", []),
    ]


def test_create_job_accepts_images_and_text_with_columns(client):
    res = client.post(
        "/jobs",
        files=[upload("scan.JPG"), upload("a.pdf"), upload("a.png"), upload("notes.txt"), upload("po.docx")],
        data={"columns": "Invoice number, Total ,\ninvoice NUMBER,"},
    )

    assert res.status_code == 202
    body = res.json()
    assert body["files"] == ["scan.JPG", "a.pdf", "a.png", "notes.txt", "po.docx"]
    assert body["columns"] == ["Invoice number", "Total"]
    assert all(m["columns"] == ["Invoice number", "Total"] for m in client.published)
    assert client.get(f"/jobs/{body['job_id']}").json()["columns"] == ["Invoice number", "Total"]

    res = client.post("/jobs", files=[upload("a.pdf")], data={"columns": '["PO #", "Qty, ordered"]'})
    assert res.json()["columns"] == ["PO #", "Qty, ordered"]


def test_column_validation(client, monkeypatch):
    assert client.post("/jobs", files=[upload("a.pdf")], data={"columns": '{"a": 1}'}).status_code == 400
    assert client.post("/jobs", files=[upload("a.pdf")], data={"columns": "x" * 101}).status_code == 400
    monkeypatch.setattr(app_module, "MAX_COLUMNS", 1)
    assert client.post("/jobs", files=[upload("a.pdf")], data={"columns": "a,b"}).status_code == 400
    assert client.published == []


def test_same_stem_different_types_keep_separate_results(client):
    job_id = client.post("/jobs", files=[upload("a.pdf"), upload("a.png")]).json()["job_id"]
    app_module.store.save_result(worker_result(job_id, "a.png"))

    body = client.get(f"/jobs/{job_id}").json()

    assert body["status"] == "processing"
    assert body["files"] == ["a.pdf", "a.png"]
    assert [r["filename"] for r in body["results"]] == ["a.png"]


def test_create_job_validation(client, monkeypatch):
    assert client.post("/jobs", files=[("pdfs", ("x.exe", b"x", "application/octet-stream"))]).status_code == 400
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
        {"filename": "a.pdf", "structured_data": {"extraction": []}, "fields": FIELDS},
        {"filename": "b.pdf", "error": "OCR failed"},
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
    assert [r["filename"] for r in body["results"]] == ["a.pdf", "b.pdf"]
    assert os.listdir(app_module.UPLOAD_FOLDER) == []


def test_process_times_out_with_job_id(client, monkeypatch):
    monkeypatch.setattr(app_module, "PROCESS_TIMEOUT", 0)
    client.post("/upload", files=[pdf("a.pdf")])

    body = client.post("/process").json()

    assert body["success"] is False
    assert body["job_id"] in body["error"]


def test_process_with_nothing_uploaded(client):
    assert client.post("/process").json() == {"success": False, "error": "No uploaded PDFs to process"}


class FakeS3:
    def __init__(self, fail_after=None):
        self.objects, self.deleted, self.fail_after = {}, [], fail_after

    def put_object(self, Bucket, Key, Body):
        if self.fail_after is not None and len(self.objects) >= self.fail_after:
            raise EndpointConnectionError(endpoint_url="http://s3")
        self.objects[Key] = Body

    def delete_objects(self, Bucket, Delete):
        self.deleted += [o["Key"] for o in Delete["Objects"]]


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(object_store, "STORAGE_BUCKET", "uploads-bucket")
    monkeypatch.setattr(object_store, "_s3", lambda: fake)
    return fake


def test_with_a_bucket_messages_carry_object_keys_not_files(client, s3):
    body = client.post("/jobs", files=[pdf("a.pdf", b"AAA"), pdf("b.pdf", b"BBB")]).json()

    keys = [f"uploads/{body['job_id']}/a.pdf", f"uploads/{body['job_id']}/b.pdf"]
    assert [m["file_key"] for m in client.published] == keys
    assert not any("file_b64" in m for m in client.published)
    assert s3.objects == {keys[0]: b"AAA", keys[1]: b"BBB"}


def test_storage_outage_returns_503_and_cleans_up(client, s3, tmp_path):
    s3.fail_after = 1

    res = client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf")])

    assert res.status_code == 503
    assert client.published == []
    assert not os.listdir(tmp_path / "storage" / "jobs")
    assert len(s3.deleted) == 1  # the file uploaded before the outage


def test_queue_down_deletes_uploaded_objects(client, s3, monkeypatch):
    def down(messages):
        raise AMQPConnectionError("refused")

    monkeypatch.setattr(app_module.broker, "publish_jobs", down)

    assert client.post("/jobs", files=[pdf("a.pdf")]).status_code == 503
    assert s3.deleted == list(s3.objects)


KEY = "AIzaSyTestKey-0123456789_abcdefghijk"


def test_keyless_job_returns_sample_data_without_queueing(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_WITHOUT_KEY", True)
    r = client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf")])
    assert r.status_code == 202
    body = r.json()
    assert body["demo"] is True and body["status"] == "done"
    assert client.published == []  # no worker, no model call

    status = client.get(f"/jobs/{body['job_id']}").json()
    assert status["status"] == "done" and status["demo"] is True
    first = status["results"][0]
    assert first["demo"] is True
    assert first["structured_data"]["extraction"][0]["header"]["purchase_order_number"] == "DEMO-1001"
    po = first["fields"]["rows"][0]["PO number"]
    assert po["value"] == "DEMO-1001" and po["source"]["line"] == 2


def test_keyless_job_with_columns_returns_sample_rows(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_WITHOUT_KEY", True)
    r = client.post("/jobs", files=[pdf("a.pdf")], data={"columns": '["PO number", "Quantity", "Colour"]'})
    result = client.get(f"/jobs/{r.json()['job_id']}").json()["results"][0]
    assert "structured_data" not in result
    assert result["fields"]["columns"] == ["PO number", "Quantity", "Colour"]
    rows = result["fields"]["rows"]
    assert len(rows) == 3  # one per sample line item
    assert [row["Quantity"]["value"] for row in rows] == ["40", "6", "12"]
    assert rows[0]["PO number"]["value"] == "DEMO-1001"
    assert rows[0]["Colour"] == {"value": "Sample Colour", "source": None}


def test_users_key_is_forwarded_to_the_workers_only(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_WITHOUT_KEY", True)
    r = client.post("/jobs", files=[pdf("a.pdf")], headers={"X-Gemini-Api-Key": f"  {KEY} "})
    assert r.status_code == 202 and r.json()["demo"] is False
    assert [m["api_key"] for m in client.published] == [KEY]
    assert KEY not in r.text
    assert KEY not in client.get(f"/jobs/{r.json()['job_id']}").text


def test_keyless_job_uses_the_workers_key_when_demo_is_off(client):
    r = client.post("/jobs", files=[pdf("a.pdf")])
    assert r.json()["demo"] is False
    assert "api_key" not in client.published[0]


def test_malformed_key_is_rejected(client):
    r = client.post("/jobs", files=[pdf("a.pdf")], headers={"X-Gemini-Api-Key": "not a key!"})
    assert r.status_code == 400
    assert client.published == []


def test_config_reports_demo_mode(client, monkeypatch):
    monkeypatch.setattr(app_module, "DEMO_WITHOUT_KEY", True)
    assert client.get("/config").json() == {"demo_without_key": True}
