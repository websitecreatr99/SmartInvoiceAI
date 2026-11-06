"""Run the worker's pipeline inside the API process instead of on worker pods (INLINE_WORKER=1).

For single-service hosting (e.g. a free Render web service): no RabbitMQ and no separate
worker. Jobs go to an in-process thread pool that calls the worker branch's own
`process_message`, so extraction, validation and source citations are identical; results
are handed to the same `on_result` the RabbitMQ result consumer uses.

The worker code is vendored under worker/ (scripts/sync_worker.sh). Compared with RabbitMQ
there is no redelivery after a crash: jobs in flight when the process restarts are lost.
"""
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List

logger = logging.getLogger("inline_worker")

WORKER_DIR = os.getenv("WORKER_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker"))
# One document at a time keeps memory flat on small hosts; Gemini does the heavy lifting remotely.
CONCURRENCY = int(os.getenv("INLINE_CONCURRENCY", "1"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("INLINE_RETRY_DELAY_SECONDS", "10"))
# Small models (Flash-Lite) now and then return JSON that fails the schema even after the fixing
# parser; a fresh attempt usually works. Only these errors are retried, so a bad file isn't re-run.
MODEL_OUTPUT_ERRORS = ("LLM extraction returned no data", "Validation Error")


def _retry_model_output(result: dict) -> bool:
    return not result.get("ok") and str(result.get("error", "")).startswith(MODEL_OUTPUT_ERRORS)


class InlineWorker:
    def __init__(self, on_result: Callable[[dict], bool]):
        self.on_result = on_result
        self._pool = ThreadPoolExecutor(max_workers=CONCURRENCY, thread_name_prefix="inline-worker")
        self._pipeline = None
        self._lock = threading.Lock()

    def _load(self):
        # Imported on first use: LangChain takes a few seconds to load, and /health should answer at once.
        with self._lock:
            if self._pipeline is None:
                if WORKER_DIR not in sys.path:
                    sys.path.insert(0, WORKER_DIR)
                import worker  # worker/worker.py from the worker branch

                self._pipeline = (worker, worker.Worker())
                logger.info(f"Inline worker ready (OCR_ENGINE={worker.OCR_ENGINE}, model={worker.GEMINI_MODEL})")
        return self._pipeline

    def warm_up(self):
        self._pool.submit(self._load)

    def submit(self, messages: List[dict]):
        for message in messages:
            self._pool.submit(self._run, message)

    def _run(self, message: dict):
        try:
            module, w = self._load()
            for attempt in range(1, MAX_ATTEMPTS + 1):
                result = module.process_message(message, w.model_handler, w.read_document, w.handler)
                transient = result.pop("retryable", False)
                bad_output = attempt == 1 and _retry_model_output(result)
                if not (transient or bad_output) or attempt == MAX_ATTEMPTS:
                    break
                reason = "temporary failure" if transient else "unusable model output"
                logger.warning(f"Job {message.get('job_id')}: {reason}, retry {attempt}/{MAX_ATTEMPTS - 1}")
                time.sleep(RETRY_DELAY_SECONDS * attempt if transient else 1)
        except Exception as e:  # process_message never raises; this guards the loading step
            logger.exception("Inline worker failed")
            result = {"job_id": message.get("job_id"), "filename": message.get("filename"), "ok": False, "error": str(e)}
        try:
            self.on_result(result)
        except Exception:
            logger.exception("Failed to store result")

    def stop(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
