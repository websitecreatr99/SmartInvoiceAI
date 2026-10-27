import pytest
from fastapi.testclient import TestClient
from pika.exceptions import AMQPConnectionError
from prometheus_client import REGISTRY

import app as app_module
from job_store import JobStore


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    upload = tmp_path / "data"
    upload.mkdir()
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", str(upload))
    monkeypatch.setattr(app_module, "store", JobStore(str(tmp_path / "storage")))
    monkeypatch.setattr(app_module.broker, "publish_jobs", lambda messages: None)
    return TestClient(app_module.app)


def pdf(name):
    return ("pdfs", (name, b"%PDF-1.4", "application/pdf"))


def test_metrics_endpoint_exposes_prometheus_text(client):
    client.get("/health")
    res = client.get("/metrics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    assert "invoiceai_api_requests_total" in res.text


def test_requests_are_labelled_by_route_template(client):
    before = sample("invoiceai_api_requests_total", method="GET", route="/jobs/{job_id}", status="404")
    client.get("/jobs/00000000-0000-0000-0000-000000000001")
    client.get("/jobs/00000000-0000-0000-0000-000000000002")
    assert sample("invoiceai_api_requests_total", method="GET", route="/jobs/{job_id}", status="404") == before + 2
    assert sample("invoiceai_api_request_duration_seconds_count", method="GET", route="/jobs/{job_id}") >= 2


def test_job_submission_counts_jobs_and_pdfs(client):
    jobs_before = sample("invoiceai_api_jobs_submitted_total", endpoint="jobs")
    pdfs_before = sample("invoiceai_api_pdfs_submitted_total")
    client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf"), pdf("c.pdf")])
    assert sample("invoiceai_api_jobs_submitted_total", endpoint="jobs") == jobs_before + 1
    assert sample("invoiceai_api_pdfs_submitted_total") == pdfs_before + 3


def test_publish_failure_is_counted(client, monkeypatch):
    def down(messages):
        raise AMQPConnectionError("refused")

    monkeypatch.setattr(app_module.broker, "publish_jobs", down)
    before = sample("invoiceai_api_publish_failures_total")
    assert client.post("/jobs", files=[pdf("a.pdf")]).status_code == 503
    assert sample("invoiceai_api_publish_failures_total") == before + 1


def test_results_and_job_duration(client):
    job_id = client.post("/jobs", files=[pdf("a.pdf"), pdf("b.pdf")]).json()["job_id"]
    ok_before = sample("invoiceai_api_results_received_total", status="ok")
    err_before = sample("invoiceai_api_results_received_total", status="error")
    unknown_before = sample("invoiceai_api_results_received_total", status="unknown_job")
    jobs_done_before = sample("invoiceai_api_job_duration_seconds_count")

    app_module.on_result({"job_id": job_id, "filename": "a.pdf", "ok": True, "structured_data": {"extraction": []}})
    assert sample("invoiceai_api_job_duration_seconds_count") == jobs_done_before  # job not finished yet
    app_module.on_result({"job_id": job_id, "filename": "b.pdf", "ok": False, "error": "OCR failed"})
    # A redelivered result for an already finished job must not count the job twice.
    app_module.on_result({"job_id": job_id, "filename": "b.pdf", "ok": False, "error": "OCR failed"})
    app_module.on_result({"job_id": "00000000-0000-0000-0000-000000000000", "filename": "x.pdf", "ok": True})

    assert sample("invoiceai_api_results_received_total", status="ok") == ok_before + 1
    assert sample("invoiceai_api_results_received_total", status="error") == err_before + 2
    assert sample("invoiceai_api_results_received_total", status="unknown_job") == unknown_before + 1
    assert sample("invoiceai_api_job_duration_seconds_count") == jobs_done_before + 1
