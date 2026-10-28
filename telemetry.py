"""Worker observability: Prometheus metrics (scraped by the tracking stack) and
Langfuse traces for LLM cost/latency. Langfuse is enabled only when
LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set. Prompts and outputs hold customer
documents, so Langfuse gets timings, tokens and cost only unless LANGFUSE_CAPTURE_CONTENT=true.
"""
import os
import time
from contextlib import contextmanager
from typing import Optional

from langchain_core.callbacks import BaseCallbackHandler
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from src.logger_config import setup_logger

logger = setup_logger(__name__)

# Gemini list prices in USD per 1M tokens; override when pricing or the model changes.
INPUT_USD_PER_1M = float(os.getenv("LLM_INPUT_USD_PER_1M", "0.30"))
OUTPUT_USD_PER_1M = float(os.getenv("LLM_OUTPUT_USD_PER_1M", "2.50"))

DURATION_BUCKETS = (0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600)

PDFS = Counter("invoiceai_worker_pdfs_total", "PDFs processed by this worker", ["status"])
PDF_SECONDS = Histogram("invoiceai_worker_pdf_duration_seconds", "End-to-end time per PDF", buckets=DURATION_BUCKETS)
STAGE_SECONDS = Histogram(
    "invoiceai_worker_stage_duration_seconds", "Time per pipeline stage", ["stage"], buckets=DURATION_BUCKETS
)
JOBS_RETRIED = Counter("invoiceai_worker_jobs_retried_total", "Jobs requeued after a temporary failure")
JOBS_DEAD_LETTERED = Counter(
    "invoiceai_worker_jobs_dead_lettered_total", "Jobs parked in the DLQ after repeatedly crashing or hanging the worker"
)
IN_PROGRESS = Gauge("invoiceai_worker_in_progress", "PDFs currently being processed")
LLM_CALLS = Counter("invoiceai_llm_calls_total", "LLM calls", ["model", "status"])
LLM_SECONDS = Histogram("invoiceai_llm_latency_seconds", "LLM call latency", ["model"], buckets=DURATION_BUCKETS)
LLM_TOKENS = Counter("invoiceai_llm_tokens_total", "LLM tokens used", ["model", "type"])
LLM_COST = Counter("invoiceai_llm_cost_usd_total", "Estimated LLM spend in USD", ["model"])

_langfuse = None


def init_series(model: str):
    """Export every labelled series at zero, so dashboards show 0 / $0 rather than "No data"
    before the first PDF or LLM call."""
    for status in ("ok", "error", "retry"):
        PDFS.labels(status)
    for status in ("ok", "error"):
        LLM_CALLS.labels(model, status)
    for name in ("ocr", "llm", "validate"):
        STAGE_SECONDS.labels(name)
    for kind in ("input", "output"):
        LLM_TOKENS.labels(model, kind)
    LLM_COST.labels(model)
    LLM_SECONDS.labels(model)


def start(metrics_port: int, model: str):
    """Expose /metrics and connect to Langfuse if configured."""
    global _langfuse
    init_series(model)
    if metrics_port:
        start_http_server(metrics_port)
        logger.info(f"Prometheus metrics on :{metrics_port}/metrics")
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        from langfuse import Langfuse

        capture = os.getenv("LANGFUSE_CAPTURE_CONTENT", "false").lower() == "true"
        _langfuse = Langfuse(mask=None if capture else redact)
        logger.info(f"Langfuse tracing enabled ({os.getenv('LANGFUSE_HOST', 'https://cloud.langfuse.com')})")


def redact(data=None, **kwargs):
    """Langfuse mask: drop span inputs/outputs (OCR text, prompts, extracted fields)."""
    return None if data is None else "[redacted]"


def shutdown():
    if _langfuse:
        _langfuse.flush()


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * INPUT_USD_PER_1M / 1e6 + output_tokens * OUTPUT_USD_PER_1M / 1e6


class UsageCallback(BaseCallbackHandler):
    """Turns LangChain LLM events into latency, token and cost metrics."""

    def __init__(self, model: str):
        self.model = model
        self._started = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self._started[run_id] = time.perf_counter()

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        self._started[run_id] = time.perf_counter()

    def on_llm_end(self, response, *, run_id, **kwargs):
        started = self._started.pop(run_id, None)
        if started is not None:
            LLM_SECONDS.labels(self.model).observe(time.perf_counter() - started)
        LLM_CALLS.labels(self.model, "ok").inc()

        usage = {}
        try:
            usage = response.generations[0][0].message.usage_metadata or {}
        except (AttributeError, IndexError):
            usage = (response.llm_output or {}).get("usage_metadata") or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        LLM_TOKENS.labels(self.model, "input").inc(input_tokens)
        LLM_TOKENS.labels(self.model, "output").inc(output_tokens)
        LLM_COST.labels(self.model).inc(cost_usd(input_tokens, output_tokens))

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._started.pop(run_id, None)
        LLM_CALLS.labels(self.model, "error").inc()


def llm_callbacks(model: str) -> list:
    callbacks = [UsageCallback(model)]
    if _langfuse:
        from langfuse.langchain import CallbackHandler

        # Nests the Gemini generation (tokens, cost, latency) under the current PDF span.
        callbacks.append(CallbackHandler())
    return callbacks


@contextmanager
def trace_pdf(job_id: Optional[str], filename: str):
    """One Langfuse trace per PDF, grouped into a session per job."""
    if not _langfuse:
        yield None
        return
    with _langfuse.start_as_current_span(name="process_pdf", input={"job_id": job_id, "filename": filename}) as span:
        span.update_trace(name="invoice-extraction", session_id=job_id, tags=["worker"])
        yield span


@contextmanager
def stage(name: str):
    """Time a pipeline stage for Prometheus, and as a Langfuse span when tracing."""
    started = time.perf_counter()
    try:
        if _langfuse:
            with _langfuse.start_as_current_span(name=name):
                yield
        else:
            yield
    finally:
        STAGE_SECONDS.labels(name).observe(time.perf_counter() - started)


def record_pdf(status: str, seconds: float, span=None, error: Optional[str] = None):
    """`status`: ok, error, or retry (failed temporarily and will be tried again)."""
    PDFS.labels(status).inc()
    PDF_SECONDS.observe(seconds)
    if span is not None:
        if status == "ok":
            span.update(output={"ok": True})
        else:
            level = "WARNING" if status == "retry" else "ERROR"
            span.update(output={"ok": False}, level=level, status_message=error)
