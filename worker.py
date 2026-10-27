"""RabbitMQ worker: consumes one PDF per message, runs OCR + LLM extraction, publishes the result.

Run as many copies (pods) as needed. RabbitMQ hands each message to exactly one
consumer, and prefetch=1 means a busy pod never holds queued work, so load spreads
evenly across pods.
"""
import base64
import functools
import json
import os
import signal
import tempfile
import threading
import time

import pika
from pika.exceptions import AMQPConnectionError

import telemetry
from src.common import DataExtractionHandler
from src.logger_config import setup_logger

logger = setup_logger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
JOBS_QUEUE = os.getenv("JOBS_QUEUE", "invoice.jobs")
RESULTS_QUEUE = os.getenv("RESULTS_QUEUE", "invoice.results")
PREFETCH = int(os.getenv("WORKER_PREFETCH", "1"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ALIVE_FILE = os.getenv("ALIVE_FILE", os.path.join(tempfile.gettempdir(), "worker-alive"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))


def process_message(payload: dict, model_handler, extract_text_from_pdf, handler: DataExtractionHandler) -> dict:
    """Turn one job message into one result message. Never raises: failures become error results."""
    job_id = payload.get("job_id")
    filename = os.path.basename(payload.get("filename") or "document.pdf")
    result = {"job_id": job_id, "filename": filename}
    started = time.perf_counter()
    telemetry.IN_PROGRESS.inc()
    with telemetry.trace_pdf(job_id, filename) as span:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pdf_path = os.path.join(tmp, filename)
                with open(pdf_path, "wb") as f:
                    f.write(base64.b64decode(payload["pdf_b64"]))

                with telemetry.stage("ocr"):
                    ocr_lines = extract_text_from_pdf(pdf_path, tmp)
                ocr_text = "\n".join(f"{text} (conf: {conf})" for text, conf in ocr_lines)

            with telemetry.stage("llm"):
                extracted = model_handler.extract_with_gemini(
                    ocr_text=ocr_text, callbacks=telemetry.llm_callbacks(GEMINI_MODEL)
                )
            if not extracted:
                raise RuntimeError("LLM extraction returned no data")

            with telemetry.stage("validate"):
                validated = handler.validate_data(extracted)
            if validated.startswith("Validation Error"):
                raise RuntimeError(validated)

            result.update(ok=True, structured_data=json.loads(validated))
        except Exception as e:
            logger.error(f"Job {job_id}: failed on {filename}: {e}", exc_info=True)
            result.update(ok=False, error=str(e))
        finally:
            telemetry.IN_PROGRESS.dec()
            telemetry.record_pdf(result.get("ok", False), time.perf_counter() - started, span, result.get("error"))
    return result


def touch_alive():
    with open(ALIVE_FILE, "w") as f:
        f.write(str(time.time()))


class Worker:
    def __init__(self):
        # Heavy imports (PaddleOCR, LangChain) happen once per process.
        from ocr_pipeline import ModelHandler, extract_text_from_pdf

        self.model_handler = ModelHandler(GEMINI_MODEL)
        self.extract_text_from_pdf = extract_text_from_pdf
        self.handler = DataExtractionHandler()
        self.connection = None
        self.channel = None
        self.busy = None
        self.stopping = False

    def on_message(self, channel, method, properties, body):
        # Work runs in a thread so this connection keeps answering heartbeats during long jobs.
        self.busy = threading.Thread(target=self.work, args=(method.delivery_tag, body), daemon=True)
        self.busy.start()

    def work(self, delivery_tag, body):
        try:
            payload = json.loads(body)
            logger.info(f"Processing job {payload.get('job_id')} file {payload.get('filename')}")
            result = process_message(payload, self.model_handler, self.extract_text_from_pdf, self.handler)
        except Exception as e:
            result = {"job_id": None, "filename": None, "ok": False, "error": f"Malformed message: {e}"}
        self.connection.add_callback_threadsafe(functools.partial(self.finish, delivery_tag, result))

    def finish(self, delivery_tag, result):
        # Publish the result before acking, so a crash in between re-runs the job instead of losing it.
        self.channel.basic_publish(
            exchange="",
            routing_key=RESULTS_QUEUE,
            body=json.dumps(result),
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent, content_type="application/json"),
        )
        self.channel.basic_ack(delivery_tag)
        logger.info(f"Finished job {result.get('job_id')} file {result.get('filename')} ok={result.get('ok')}")

    def heartbeat(self):
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
                self.channel.queue_declare(queue=JOBS_QUEUE, durable=True)
                self.channel.queue_declare(queue=RESULTS_QUEUE, durable=True)
                self.channel.basic_qos(prefetch_count=PREFETCH)
                self.channel.basic_consume(queue=JOBS_QUEUE, on_message_callback=self.on_message)
                self.heartbeat()
                logger.info(f"Worker consuming from {JOBS_QUEUE}")
                self.channel.start_consuming()

                # Let an in-flight job finish and ack before closing.
                while self.busy and self.busy.is_alive():
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
    telemetry.start(METRICS_PORT)
    Worker().run()
