import base64
import json

import worker
from src.common import DataExtractionHandler
from src.document_reader import Line

PDF = base64.b64encode(b"%PDF-1.4 stub").decode()


class FakeModel:
    def __init__(self, data):
        self.data = data
        self.seen = None

    def extract_with_gemini(self, ocr_text, callbacks=None):
        self.seen = ocr_text
        self.callbacks = callbacks
        return self.data

    def extract_columns(self, ocr_text, columns, callbacks=None):
        self.seen = ocr_text
        self.columns = columns
        return self.data


def fake_ocr(path, out_dir):
    with open(path, "rb") as f:
        assert f.read() == b"%PDF-1.4 stub"
    return [Line(1, "INVOICE 42", 0.99), Line(2, "Qty 5", 0.9)]


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
    row = result["fields"]["rows"][0]
    assert row["Job number"] == {
        "value": "42",
        "source": {"page": 1, "line": 1, "text": "INVOICE 42", "confidence": 0.99},
    }
    assert row["Vendor"] == {"value": None, "source": None}


def test_requested_columns_cite_their_source_line():
    model = FakeModel({"rows": [
        {"cells": [{"column": "invoice no", "value": 42, "line": 1}, {"column": "Qty", "value": "5", "line": 99}]},
        {"cells": [{"column": "Unknown", "value": "x", "line": 1}]},
    ]})

    result = worker.process_message(
        {"job_id": "j1", "filename": "a.png", "file_b64": PDF, "columns": [" Invoice No ", "Qty", ""]},
        model, fake_ocr, DataExtractionHandler(),
    )

    assert result["ok"] is True
    assert "structured_data" not in result
    assert model.columns == ["Invoice No", "Qty"]
    assert "[L2] (p2) Qty 5" in model.seen
    assert result["fields"]["columns"] == ["Invoice No", "Qty"]
    # Cited line out of range: found by matching the value instead. Rows with no requested columns are dropped.
    assert result["fields"]["rows"] == [{
        "Invoice No": {"value": "42", "source": {"page": 1, "line": 1, "text": "INVOICE 42", "confidence": 0.99}},
        "Qty": {"value": "5", "source": {"page": 2, "line": 2, "text": "Qty 5", "confidence": 0.9}},
    }]


def test_document_without_text_is_an_error():
    result = worker.process_message(
        {"job_id": "j1", "filename": "a.png", "file_b64": PDF}, FakeModel({}), lambda p, d: [], DataExtractionHandler()
    )
    assert result == {"job_id": "j1", "filename": "a.png", "ok": False, "error": "No text found in document"}


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
