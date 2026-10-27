import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Kept free of OCR/LLM imports so the API can enqueue jobs without loading them.
celery_app = Celery("invoiceai", broker=REDIS_URL, backend=REDIS_URL, include=["tasks"])

celery_app.conf.update(
    task_track_started=True,
    # A job goes back on the queue if its worker dies mid-run.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Jobs are long; don't let one worker hoard queued jobs while others sit idle.
    worker_prefetch_multiplier=1,
    task_time_limit=int(os.getenv("JOB_TIME_LIMIT", "1800")),
    result_expires=int(os.getenv("RESULT_TTL", str(24 * 3600))),
)
