"""RabbitMQ worker: consumes one document per message, runs OCR + LLM extraction, publishes the result.

Run as many copies (pods) as needed. RabbitMQ hands each message to exactly one
consumer, and prefetch=1 means a busy pod never holds queued work, so load spreads
evenly across pods.
"""
import functools
import json
import os
import signal
import sys
import tempfile
import threading
import time

import pika
from pika.exceptions import AMQPConnectionError

import telemetry
from src import queues, sources, storage
from src.common import DataExtractionHandler
from src.document_reader import read_document
from src.errors import TransientError
from src.logger_config import setup_logger

logger = setup_logger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
PREFETCH = int(os.getenv("WORKER_PREFETCH", "1"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ALIVE_FILE = os.getenv("ALIVE_FILE", os.path.join(tempfile.gettempdir(), "worker-alive"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))
# Tries per job when it fails for a temporary reason (Gemini 429/5xx, storage outage).
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
MAX_FILE_BYTES = int(float(os.getenv("MAX_FILE_MB", "25")) * 1048576)
# A job running longer than this is presumed hung: the worker exits so the pod restarts
# and RabbitMQ redelivers the message (which counts towards MAX_REDELIVERIES).
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "540"))


def requested_columns(payload: dict) -> list:
    columns = payload.get("columns") or []
    return [c.strip() for c in columns if isinstance(c, str) and c.strip()]


def process_message(payload: dict, model_handler, read_document, handler: DataExtractionHandler,
                    download=storage.download) -> dict:
    """Turn one job message into one result message. Never raises: failures become error results,
    marked `retryable` when a later attempt could succeed.

    `read_document(path, out_dir)` returns the document's text as src.document_reader.Line objects.
    With `columns` in the payload only those are extracted; otherwise the invoice schema is used.
    Either way the result carries `fields`: table rows whose cells cite their source line.
    """
    job_id = payload.get("job_id")
    filename = os.path.basename(payload.get("filename") or "document.pdf")
    columns = requested_columns(payload)
    result = {"job_id": job_id, "filename": filename}
    started = time.perf_counter()
    telemetry.IN_PROGRESS.inc()
    with telemetry.trace_pdf(job_id, filename) as span:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, filename)
                download(payload, path, MAX_FILE_BYTES)

                with telemetry.stage("ocr"):
                    lines = read_document(path, tmp)
            if not lines:
                raise RuntimeError("No text found in document")

            callbacks = telemetry.llm_callbacks(GEMINI_MODEL)
            if columns:
                with telemetry.stage("llm"):
                    extracted = model_handler.extract_columns(
                        ocr_text=sources.numbered_text(lines), columns=columns, callbacks=callbacks
                    )
                if not extracted:
                    raise RuntimeError("LLM extraction returned no data")
                with telemetry.stage("validate"):
                    fields = sources.column_fields(extracted, columns, lines)
                result.update(ok=True, fields=fields)
            else:
                ocr_text = "\n".join(
                    line.text if line.confidence is None else f"{line.text} (conf: {line.confidence})"
                    for line in lines
                )
                with telemetry.stage("llm"):
                    extracted = model_handler.extract_with_gemini(ocr_text=ocr_text, callbacks=callbacks)
                if not extracted:
                    raise RuntimeError("LLM extraction returned no data")

                with telemetry.stage("validate"):
                    validated = handler.validate_data(extracted)
                if validated.startswith("Validation Error"):
                    raise RuntimeError(validated)

                structured = json.loads(validated)
                result.update(ok=True, structured_data=structured, fields=sources.invoice_fields(structured, lines))
        except TransientError as e:
            logger.warning(f"Job {job_id}: temporary failure on {filename}: {e}")
            result.update(ok=False, error=str(e), retryable=True)
        except Exception as e:
            logger.error(f"Job {job_id}: failed on {filename}: {e}", exc_info=True)
            result.update(ok=False, error=str(e))
        finally:
            telemetry.IN_PROGRESS.dec()
            status = "ok" if result.get("ok") else "retry" if result.get("retryable") else "error"
            telemetry.record_pdf(status, time.perf_counter() - started, span, result.get("error"))
    return result


def touch_alive():
    with open(ALIVE_FILE, "w") as f:
        f.write(str(time.time()))


def parse_job(body) -> dict:
    try:
        payload = json.loads(body)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


class Worker:
    def __init__(self):
        # Heavy imports (PaddleOCR, LangChain) happen once per process.
        from ocr_pipeline import ModelHandler, ocr_pages

        self.model_handler = ModelHandler(GEMINI_MODEL)
        self.read_document = functools.partial(read_document, ocr_pages=ocr_pages)
        self.handler = DataExtractionHandler()
        self.connection = None
        self.channel = None
        self.busy = None
        self.job_started = None
        self.stopping = False
        self.timed_out = False

    def on_message(self, channel, method, properties, body):
        redeliveries = queues.prior_deliveries(properties.headers)
        if redeliveries >= queues.MAX_REDELIVERIES:
            self.give_up(method.delivery_tag, body, redeliveries)
            return
        # Work runs in a thread so this connection keeps answering heartbeats during long jobs.
        self.job_started = time.monotonic()
        self.busy = threading.Thread(target=self.work, args=(method.delivery_tag, body), daemon=True)
        self.busy.start()

    def work(self, delivery_tag, body):
        payload = None
        try:
            payload = json.loads(body)
            logger.info(f"Processing job {payload.get('job_id')} file {payload.get('filename')}")
            result = process_message(payload, self.model_handler, self.read_document, self.handler)
        except Exception as e:
            result = {"job_id": None, "filename": None, "ok": False, "error": f"Malformed message: {e}"}
        self.connection.add_callback_threadsafe(functools.partial(self.finish, delivery_tag, result, payload))

    def publish(self, queue, body):
        self.channel.basic_publish(
            exchange="",
            routing_key=queue,
            body=body,
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent, content_type="application/json"),
        )

    def finish(self, delivery_tag, result, payload=None):
        # Publish before acking, so a crash in between re-runs the job instead of losing it.
        self.job_started = None
        attempt = payload.get("attempt") if isinstance(payload, dict) else None
        attempt = attempt if isinstance(attempt, int) else 1
        if result.pop("retryable", False) and attempt < MAX_ATTEMPTS:
            self.publish(queues.RETRY_QUEUE, json.dumps({**payload, "attempt": attempt + 1}))
            self.channel.basic_ack(delivery_tag)
            telemetry.JOBS_RETRIED.inc()
            logger.warning(
                f"Job {result.get('job_id')} attempt {attempt}/{MAX_ATTEMPTS} failed temporarily; "
                f"retrying in {queues.RETRY_DELAY_SECONDS}s"
            )
            return
        self.publish(queues.RESULTS_QUEUE, json.dumps(result))
        self.channel.basic_ack(delivery_tag)
        logger.info(f"Finished job {result.get('job_id')} file {result.get('filename')} ok={result.get('ok')}")

    def give_up(self, delivery_tag, body, redeliveries):
        """The message already crashed or hung pods `redeliveries` times: park it in the DLQ
        and tell the API, rather than let it take down more pods."""
        payload = parse_job(body)
        logger.error(f"Job {payload.get('job_id')} lost {redeliveries} deliveries; moving it to {queues.DEAD_LETTER_QUEUE}")
        self.publish(queues.DEAD_LETTER_QUEUE, body)
        telemetry.JOBS_DEAD_LETTERED.inc()
        self.finish(delivery_tag, {
            "job_id": payload.get("job_id"),
            "filename": payload.get("filename"),
            "ok": False,
            "error": f"Document could not be processed: it crashed or timed out the worker {redeliveries} times",
        })

    def hung(self) -> bool:
        return self.job_started is not None and time.monotonic() - self.job_started > JOB_TIMEOUT_SECONDS

    def heartbeat(self):
        if self.hung():
            if not self.timed_out:
                logger.error(f"Job running for over {JOB_TIMEOUT_SECONDS}s; exiting so the pod restarts")
                self.timed_out = True
                self.stop()
        else:
            touch_alive()
        self.connection.call_later(15, self.heartbeat)

    def stop(self, *_):
        logger.info("Shutdown requested; finishing current message")
        self.stopping = True
        if self.connection and self.connection.is_open:
            self.connection.add_callback_threadsafe(self.channel.stop_consuming)

    def run(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        params = pika.URLParameters(RABBITMQ_URL)
        params.heartbeat = 60

        while not self.stopping:
            try:
                self.connection = pika.BlockingConnection(params)
                self.channel = self.connection.channel()
                queues.declare(self.channel)
                self.channel.basic_qos(prefetch_count=PREFETCH)
                self.channel.basic_consume(queue=queues.JOBS_QUEUE, on_message_callback=self.on_message)
                self.heartbeat()
                logger.info(f"Worker consuming from {queues.JOBS_QUEUE}")
                self.channel.start_consuming()

                # Let an in-flight job finish and ack before closing. A hung job is abandoned
                # unacked, so RabbitMQ hands it out again and counts the lost delivery.
                while self.busy and self.busy.is_alive() and not self.hung():
                    self.connection.process_data_events(time_limit=1)
                self.connection.process_data_events(time_limit=0)
                self.connection.close()
            except AMQPConnectionError as e:
                if self.stopping:
                    break
                logger.warning(f"RabbitMQ unavailable ({e}); retrying in 5s")
                time.sleep(5)
        telemetry.shutdown()


if __name__ == "__main__":
    telemetry.start(METRICS_PORT, GEMINI_MODEL)
    worker = Worker()
    worker.run()
    sys.exit(1 if worker.timed_out else 0)
