"""Stand-in for the worker pods (worker branch) that speaks the same queue protocol
but skips OCR/LLM, so the API can be tested against a real RabbitMQ quickly.

Usage: RABBITMQ_URL=... python scripts/fake_worker.py [name]
"""
import json
import os
import sys
import threading
import time

import pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
JOBS_QUEUE = os.getenv("JOBS_QUEUE", "invoice.jobs")
RESULTS_QUEUE = os.getenv("RESULTS_QUEUE", "invoice.results")


def serve(stop: threading.Event, name: str = "fake-worker", delay: float = 0.2, on_handled=None):
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=JOBS_QUEUE, durable=True)
    channel.queue_declare(queue=RESULTS_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    for method, _, body in channel.consume(JOBS_QUEUE, inactivity_timeout=0.5):
        if stop.is_set():
            break
        if method is None:
            continue
        job = json.loads(body)
        time.sleep(delay)
        result = {
            "job_id": job["job_id"],
            "filename": job["filename"],
            "ok": True,
            "structured_data": {"extraction": [{"header": {"job_name": f"processed by {name}"}, "line_items": []}]},
        }
        channel.basic_publish(exchange="", routing_key=RESULTS_QUEUE, body=json.dumps(result))
        channel.basic_ack(method.delivery_tag)
        if on_handled:
            on_handled(name, job)

    channel.cancel()
    connection.close()


if __name__ == "__main__":
    serve(threading.Event(), sys.argv[1] if len(sys.argv) > 1 else "fake-worker")
