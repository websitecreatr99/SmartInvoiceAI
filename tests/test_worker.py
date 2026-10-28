import base64
import json
import time

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

import telemetry
import worker
from src import queues, storage
from src.common import DataExtractionHandler
from src.document_reader import Line
from src.errors import TransientError

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
        ("publish", queues.RESULTS_QUEUE, {"job_id": "j1", "filename": "a.pdf", "ok": True}),
        ("ack", 7),
    ]


def test_malformed_message_is_acked_with_error():
    w = object.__new__(worker.Worker)
    finished = []

    class Conn:
        def add_callback_threadsafe(self, cb):
            cb()

    w.connection = Conn()
    w.finish = lambda tag, result, payload=None: finished.append((tag, result))

    w.work(3, b"not json")

    assert finished[0][0] == 3
    assert finished[0][1]["ok"] is False
    assert "Malformed message" in finished[0][1]["error"]


def test_validation_error_does_not_echo_document_values():
    result = worker.process_message(
        {"job_id": "j1", "filename": "a.pdf", "pdf_b64": PDF},
        FakeModel({"extraction": [{"header": {"job_name": ["SECRET-CUSTOMER-NAME"]}}]}),
        fake_ocr, DataExtractionHandler(),
    )
    assert result["ok"] is False
    assert "extraction.0.header.job_name" in result["error"]
    assert "SECRET-CUSTOMER-NAME" not in result["error"]


def test_temporary_llm_failure_is_retryable():
    class Throttled(FakeModel):
        def extract_with_gemini(self, ocr_text, callbacks=None):
            raise TransientError("Gemini unavailable: 429")

    before = telemetry.PDFS.labels("retry")._value.get()
    result = worker.process_message(
        {"job_id": "j1", "filename": "a.pdf", "pdf_b64": PDF}, Throttled(None), fake_ocr, DataExtractionHandler()
    )
    assert result == {"job_id": "j1", "filename": "a.pdf", "ok": False, "error": "Gemini unavailable: 429", "retryable": True}
    assert telemetry.PDFS.labels("retry")._value.get() == before + 1


def test_oversized_file_is_rejected_before_ocr(monkeypatch):
    monkeypatch.setattr(worker, "MAX_FILE_BYTES", 4)

    def ocr_must_not_run(path, out_dir):
        raise AssertionError("OCR ran on an oversized file")

    result = worker.process_message(
        {"job_id": "j1", "filename": "a.pdf", "file_b64": PDF}, FakeModel({}), ocr_must_not_run, DataExtractionHandler()
    )
    assert result["ok"] is False
    assert "limit" in result["error"]


def bare_worker():
    w = object.__new__(worker.Worker)  # skip __init__, which loads the OCR stack
    w.channel = FakeChannel()
    w.job_started = None
    w.timed_out = False
    return w


def test_temporary_failure_is_requeued_with_next_attempt():
    w = bare_worker()
    payload = {"job_id": "j1", "filename": "a.pdf", "file_key": "k"}

    w.finish(7, {"job_id": "j1", "ok": False, "error": "429", "retryable": True}, payload)

    assert w.channel.calls == [("publish", queues.RETRY_QUEUE, {**payload, "attempt": 2}), ("ack", 7)]


def test_last_attempt_publishes_the_error_result():
    w = bare_worker()
    payload = {"job_id": "j1", "file_key": "k", "attempt": worker.MAX_ATTEMPTS}

    w.finish(7, {"job_id": "j1", "ok": False, "error": "429", "retryable": True}, payload)

    assert w.channel.calls == [
        ("publish", queues.RESULTS_QUEUE, {"job_id": "j1", "ok": False, "error": "429"}),
        ("ack", 7),
    ]


class Method:
    delivery_tag = 9


class Props:
    def __init__(self, headers):
        self.headers = headers


def test_message_that_keeps_killing_pods_is_parked_and_reported():
    w = bare_worker()
    body = json.dumps({"job_id": "j1", "filename": "bomb.pdf", "file_key": "k"}).encode()

    w.on_message(None, Method, Props({"x-delivery-count": queues.MAX_REDELIVERIES}), body)

    assert w.channel.calls[0] == ("publish", queues.DEAD_LETTER_QUEUE, json.loads(body))
    kind, queue, result = w.channel.calls[1]
    assert (kind, queue, result["job_id"], result["ok"]) == ("publish", queues.RESULTS_QUEUE, "j1", False)
    assert "crashed or timed out" in result["error"]
    assert w.channel.calls[2] == ("ack", 9)


@pytest.mark.parametrize("headers, expected", [
    (None, 0), ({}, 0), ({"x-delivery-count": 2}, 2), ({"x-acquired-count": 3, "x-delivery-count": 1}, 3),
])
def test_prior_deliveries(headers, expected):
    assert queues.prior_deliveries(headers) == expected


def test_hung_job_stops_the_worker_instead_of_reporting_alive(monkeypatch, tmp_path):
    w = bare_worker()
    stopped, scheduled = [], []

    class Conn:
        def call_later(self, delay, cb):
            scheduled.append(delay)

    w.connection = Conn()
    w.stop = lambda *_: stopped.append(True)
    monkeypatch.setattr(worker, "ALIVE_FILE", str(tmp_path / "alive"))

    w.job_started = time.monotonic() - worker.JOB_TIMEOUT_SECONDS - 1
    w.heartbeat()

    assert stopped == [True] and w.timed_out
    assert not (tmp_path / "alive").exists()
    assert scheduled == [15]


class FakeS3:
    def __init__(self, size=10, error=None):
        self.size, self.error = size, error

    def head_object(self, Bucket, Key):
        if self.error:
            raise self.error
        return {"ContentLength": self.size}

    def download_file(self, bucket, key, path):
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4 stub")


def use_s3(monkeypatch, s3):
    monkeypatch.setattr(storage, "STORAGE_BUCKET", "bucket")
    monkeypatch.setattr(storage, "_s3", lambda: s3)


def test_file_key_is_downloaded_from_object_storage(monkeypatch):
    use_s3(monkeypatch, FakeS3())
    model = FakeModel({"extraction": []})

    result = worker.process_message({"job_id": "j1", "filename": "a.pdf", "file_key": "uploads/a.pdf"},
                                    model, fake_ocr, DataExtractionHandler())

    assert result["ok"] is True


def throttled():
    return ClientError({"Error": {"Code": "SlowDown"}, "ResponseMetadata": {"HTTPStatusCode": 503}}, "HeadObject")


@pytest.mark.parametrize("error", [throttled(), EndpointConnectionError(endpoint_url="http://s3")])
def test_storage_outage_is_temporary(monkeypatch, tmp_path, error):
    use_s3(monkeypatch, FakeS3(error=error))
    with pytest.raises(TransientError):
        storage.download({"file_key": "k"}, str(tmp_path / "a.pdf"), 100)


def test_missing_object_is_a_permanent_error(monkeypatch, tmp_path):
    use_s3(monkeypatch, FakeS3(error=ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")))
    with pytest.raises(ValueError, match="404"):
        storage.download({"file_key": "k"}, str(tmp_path / "a.pdf"), 100)


def test_large_object_is_not_downloaded(monkeypatch, tmp_path):
    use_s3(monkeypatch, FakeS3(size=101))
    with pytest.raises(ValueError, match="limit"):
        storage.download({"file_key": "k"}, str(tmp_path / "a.pdf"), 100)
    assert not (tmp_path / "a.pdf").exists()
