import json
import subprocess

import pytest
from fastapi.testclient import TestClient

import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    upload = tmp_path / "data"
    structured = tmp_path / "structured_output"
    upload.mkdir()
    structured.mkdir()
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", str(upload))
    monkeypatch.setattr(app_module, "STRUCTURED_OUTPUT_FOLDER", str(structured))
    return TestClient(app_module.app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_upload_saves_files(client):
    files = [
        ("pdfs", ("a.pdf", b"%PDF-1.4 a", "application/pdf")),
        ("pdfs", ("b.pdf", b"%PDF-1.4 b", "application/pdf")),
    ]
    res = client.post("/upload", files=files)

    assert res.status_code == 200
    assert res.json() == {"success": True, "uploaded": ["a.pdf", "b.pdf"]}
    with open(f"{app_module.UPLOAD_FOLDER}/a.pdf", "rb") as f:
        assert f.read() == b"%PDF-1.4 a"


def test_upload_strips_directory_from_filename(client, tmp_path):
    res = client.post("/upload", files=[("pdfs", ("../escape.pdf", b"x", "application/pdf"))])

    assert res.json()["uploaded"] == ["escape.pdf"]
    assert not (tmp_path / "escape.pdf").exists()


def test_delete(client):
    client.post("/upload", files=[("pdfs", ("a.pdf", b"x", "application/pdf"))])

    assert client.post("/delete", json={"filename": "a.pdf"}).json() == {"success": True, "deleted": "a.pdf"}
    res = client.post("/delete", json={"filename": "a.pdf"})
    assert res.status_code == 404
    assert res.json() == {"success": False, "error": "File not found"}


def test_process_returns_structured_output(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.subprocess, "run", lambda *a, **kw: calls.append(a))
    doc = {"extraction": [{"header": None, "line_items": []}]}
    with open(f"{app_module.STRUCTURED_OUTPUT_FOLDER}/inv.json", "w") as f:
        json.dump(doc, f)

    res = client.post("/process").json()

    assert len(calls) == 1
    assert res == {"success": True, "results": [{"filename": "inv.json", "structured_data": doc}]}


def test_process_reports_pipeline_failure(client, monkeypatch):
    def fail(*a, **kw):
        raise subprocess.CalledProcessError(1, "ocr_pipeline.py")

    monkeypatch.setattr(app_module.subprocess, "run", fail)

    res = client.post("/process").json()

    assert res["success"] is False
    assert "OCR pipeline failed" in res["error"]
