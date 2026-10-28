"""Publish one job to a real RabbitMQ and wait for a running worker to answer it.

Usage: RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F python scripts/smoke_test.py
"""
import base64
import json
import os
import sys
import time
import uuid

import pika

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.queues import JOBS_QUEUE, RESULTS_QUEUE, declare  # noqa: E402

URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
TIMEOUT = int(os.getenv("SMOKE_TIMEOUT", "300"))

connection = pika.BlockingConnection(pika.URLParameters(URL))
channel = connection.channel()
declare(channel)

job_id = str(uuid.uuid4())
# A stub PDF: OCR fails on it, so a result with ok=false still proves the worker
# consumed the job, loaded the pipeline, and published back.
message = {"job_id": job_id, "filename": "smoke.pdf", "pdf_b64": base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode()}
channel.basic_publish(
    exchange="",
    routing_key=JOBS_QUEUE,
    body=json.dumps(message),
    properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent),
)
print(f"published job {job_id}")

deadline = time.time() + TIMEOUT
while time.time() < deadline:
    method, _, body = channel.basic_get(queue=RESULTS_QUEUE, auto_ack=False)
    if method is None:
        time.sleep(2)
        continue
    result = json.loads(body)
    if result.get("job_id") != job_id:
        channel.basic_nack(method.delivery_tag, requeue=True)
        continue
    channel.basic_ack(method.delivery_tag)
    print("result:", json.dumps(result)[:300])
    ok = result.get("filename") == "smoke.pdf" and ("structured_data" in result or result.get("error"))
    print("PASS" if ok else "FAIL: unexpected result shape")
    sys.exit(0 if ok else 1)

print(f"FAIL: no result within {TIMEOUT}s")
sys.exit(1)
