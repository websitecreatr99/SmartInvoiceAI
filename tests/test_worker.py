import base64
import json

import worker
from src.common import DataExtractionHandler

PDF = base64.b64encode(b"%PDF-1.4 stub").decode()


class FakeModel:
    def __init__(self, data):
        self.data = data
        self.seen = None

    def extract_with_gemini(self, ocr_text, callbacks=None):
        self.seen = ocr_text
        self.callbacks = callbacks
        return self.data


def fake_ocr(path, out_dir):
    with open(path, "rb") as f:
        assert f.read() == b"%PDF-1.4 stub"
    return [("INVOICE 42", 0.99), ("Qty 5", 0.9)]


def test_successful_message_returns_validated_data():
    model = FakeModel({"extraction": [{"header": {"job_number": "42"}, "line_items": []}]})

    result = worker.process_message(
        {"job_id": "j1", "filename": "../a.pdf", "pdf_b64": PDF}, model, fake_ocr, DataExtractionHandler()
    )

    assert result["ok"] is True
    assert result["job_id"] == "j1"
    assert result["filename"] == "a.pdf"
    assert result["structured_data"]["extraction"][0]["header"]["job_number"] == "42"
    assert "INVOICE 42 (conf: 0.99)" in model.seen


def test_ocr_failure_becomes_error_result():
    def broken_ocr(path, out_dir):
        raise RuntimeError("unreadable PDF")

    result = worker.process_message(
        {"job_id": "j1", "filename": "a.pdf", "pdf_b64": PDF}, FakeModel({}), broken_ocr, DataExtractionHandler()
    )

    assert result == {"job_id": "j1", "filename": "a.pdf", "ok": False, "error": "unreadable PDF"}


def test_empty_llm_output_is_an_error():
    result = worker.process_message(
        {"job_id": "j1", "filename": "a.pdf", "pdf_b64": PDF}, FakeModel(None), fake_ocr, DataExtractionHandler()
    )
    assert result["ok"] is False
    assert "no data" in result["error"]


def test_schema_violation_is_an_error():
    result = worker.process_message(
        {"job_id": "j1", "filename": "a.pdf", "pdf_b64": PDF}, FakeModel({"wrong": 1}), fake_ocr, DataExtractionHandler()
    )
    assert result["ok"] is False
    assert "Validation Error" in result["error"]


class FakeChannel:
    def __init__(self):
        self.calls = []

    def basic_publish(self, exchange, routing_key, body, properties):
        self.calls.append(("publish", routing_key, json.loads(body)))

    def basic_ack(self, tag):
        self.calls.append(("ack", tag))


def test_result_is_published_before_ack():
    w = object.__new__(worker.Worker)  # skip __init__, which loads the OCR stack
    w.channel = FakeChannel()

    w.finish(7, {"job_id": "j1", "filename": "a.pdf", "ok": True})

    assert w.channel.calls == [
        ("publish", worker.RESULTS_QUEUE, {"job_id": "j1", "filename": "a.pdf", "ok": True}),
        ("ack", 7),
    ]


def test_malformed_message_is_acked_with_error():
    w = object.__new__(worker.Worker)
    finished = []

    class Conn:
        def add_callback_threadsafe(self, cb):
            cb()

    w.connection = Conn()
    w.finish = lambda tag, result: finished.append((tag, result))

    w.work(3, b"not json")

    assert finished[0][0] == 3
    assert finished[0][1]["ok"] is False
    assert "Malformed message" in finished[0][1]["error"]
