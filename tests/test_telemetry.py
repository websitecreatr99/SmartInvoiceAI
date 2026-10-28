import base64
import uuid
from contextlib import contextmanager

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from prometheus_client import REGISTRY

import telemetry
import worker
from src.common import DataExtractionHandler
from src.document_reader import Line

PDF = base64.b64encode(b"%PDF-1.4 stub").decode()
MODEL = "gemini-test"


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


class FakeModel:
    def __init__(self, data):
        self.data = data
        self.callbacks = None

    def extract_with_gemini(self, ocr_text, callbacks=None):
        self.callbacks = callbacks
        return self.data


def ocr_ok(path, out):
    return [Line(1, "INVOICE", 0.9)]


def test_successful_pdf_records_metrics():
    before_ok = sample("invoiceai_worker_pdfs_total", status="ok")
    before_ocr = sample("invoiceai_worker_stage_duration_seconds_count", stage="ocr")
    before_llm = sample("invoiceai_worker_stage_duration_seconds_count", stage="llm")
    model = FakeModel({"extraction": []})

    result = worker.process_message({"job_id": "j", "filename": "a.pdf", "pdf_b64": PDF}, model, ocr_ok, DataExtractionHandler())

    assert result["ok"] is True
    assert sample("invoiceai_worker_pdfs_total", status="ok") == before_ok + 1
    assert sample("invoiceai_worker_stage_duration_seconds_count", stage="ocr") == before_ocr + 1
    assert sample("invoiceai_worker_stage_duration_seconds_count", stage="llm") == before_llm + 1
    assert sample("invoiceai_worker_in_progress") == 0
    assert any(isinstance(cb, telemetry.UsageCallback) for cb in model.callbacks)


def test_failed_pdf_records_error_metric():
    before = sample("invoiceai_worker_pdfs_total", status="error")

    def ocr_fail(path, out):
        raise RuntimeError("bad pdf")

    result = worker.process_message({"job_id": "j", "filename": "a.pdf", "pdf_b64": PDF}, FakeModel({}), ocr_fail, DataExtractionHandler())

    assert result["ok"] is False
    assert sample("invoiceai_worker_pdfs_total", status="error") == before + 1
    assert sample("invoiceai_worker_in_progress") == 0


def test_usage_callback_counts_tokens_cost_and_latency(monkeypatch):
    monkeypatch.setattr(telemetry, "INPUT_USD_PER_1M", 0.30)
    monkeypatch.setattr(telemetry, "OUTPUT_USD_PER_1M", 2.50)
    before_in = sample("invoiceai_llm_tokens_total", model=MODEL, type="input")
    before_out = sample("invoiceai_llm_tokens_total", model=MODEL, type="output")
    before_cost = sample("invoiceai_llm_cost_usd_total", model=MODEL)
    before_calls = sample("invoiceai_llm_latency_seconds_count", model=MODEL)

    cb = telemetry.UsageCallback(MODEL)
    run_id = uuid.uuid4()
    cb.on_chat_model_start({}, [[]], run_id=run_id)
    message = AIMessage(content="{}", usage_metadata={"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200})
    cb.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=run_id)

    assert sample("invoiceai_llm_tokens_total", model=MODEL, type="input") == before_in + 1000
    assert sample("invoiceai_llm_tokens_total", model=MODEL, type="output") == before_out + 200
    # 1000 * $0.30/1M + 200 * $2.50/1M
    assert sample("invoiceai_llm_cost_usd_total", model=MODEL) == pytest.approx(before_cost + 0.0008)
    assert sample("invoiceai_llm_latency_seconds_count", model=MODEL) == before_calls + 1


def test_usage_callback_counts_errors():
    before = sample("invoiceai_llm_calls_total", model=MODEL, status="error")
    cb = telemetry.UsageCallback(MODEL)
    run_id = uuid.uuid4()
    cb.on_chat_model_start({}, [[]], run_id=run_id)
    cb.on_llm_error(RuntimeError("quota"), run_id=run_id)
    assert sample("invoiceai_llm_calls_total", model=MODEL, status="error") == before + 1


class FakeSpan:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def update_trace(self, **kw):
        self.log.append(("trace", kw))

    def update(self, **kw):
        self.log.append(("update", self.name, kw))


class FakeLangfuse:
    def __init__(self):
        self.log = []

    @contextmanager
    def start_as_current_span(self, name, **kw):
        self.log.append(("span", name))
        yield FakeSpan(self.log, name)


def test_langfuse_trace_per_pdf_with_stage_spans(monkeypatch):
    fake = FakeLangfuse()
    monkeypatch.setattr(telemetry, "_langfuse", fake)
    monkeypatch.setattr(telemetry, "llm_callbacks", lambda model: [])

    worker.process_message({"job_id": "job-1", "filename": "a.pdf", "pdf_b64": PDF}, FakeModel(None), ocr_ok, DataExtractionHandler())

    spans = [e[1] for e in fake.log if e[0] == "span"]
    assert spans == ["process_pdf", "ocr", "llm"]
    trace = next(e[1] for e in fake.log if e[0] == "trace")
    assert trace["session_id"] == "job-1"
    final = [e for e in fake.log if e[0] == "update"][-1]
    assert final[2]["level"] == "ERROR"
    assert "no data" in final[2]["status_message"]


def test_series_exported_at_zero_before_any_traffic():
    telemetry.init_series("never-called-model")
    assert REGISTRY.get_sample_value("invoiceai_llm_cost_usd_total", {"model": "never-called-model"}) == 0.0
    assert REGISTRY.get_sample_value(
        "invoiceai_llm_tokens_total", {"model": "never-called-model", "type": "output"}
    ) == 0.0
    assert REGISTRY.get_sample_value(
        "invoiceai_llm_calls_total", {"model": "never-called-model", "status": "error"}
    ) == 0.0


def test_no_langfuse_means_only_metrics_callback(monkeypatch):
    monkeypatch.setattr(telemetry, "_langfuse", None)
    callbacks = telemetry.llm_callbacks(MODEL)
    assert len(callbacks) == 1 and isinstance(callbacks[0], telemetry.UsageCallback)


def test_langfuse_mask_drops_document_content():
    assert telemetry.redact(data={"ocr_text": "ACME invoice"}) == "[redacted]"
    assert telemetry.redact(data=None) is None
