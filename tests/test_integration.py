"""End-to-end through a real RabbitMQ with fake workers. Skipped unless RABBITMQ_URL is set (CI sets it)."""
import os
import sys
import threading
import time
from collections import Counter

import pika
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(not os.getenv("RABBITMQ_URL"), reason="needs a RabbitMQ (set RABBITMQ_URL)")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import app as app_module  # noqa: E402
import fake_worker  # noqa: E402
import migrate_queues  # noqa: E402
import queues  # noqa: E402
from job_store import JobStore  # noqa: E402


@pytest.fixture
def stack(tmp_path, monkeypatch):
    upload = tmp_path / "data"
    upload.mkdir()
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", str(upload))
    monkeypatch.setattr(app_module, "store", JobStore(str(tmp_path / "storage")))

    stop = threading.Event()
    handled = Counter()
    lock = threading.Lock()

    def record(name, job):
        with lock:
            handled[name] += 1

    workers = [
        threading.Thread(target=fake_worker.serve, args=(stop, f"pod-{i}", 0.3, record), daemon=True) for i in range(3)
    ]
    for w in workers:
        w.start()

    with TestClient(app_module.app) as client:  # starts the result consumer
        yield client, handled

    stop.set()
    for w in workers:
        w.join(timeout=5)


def wait_done(client, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] == "done":
            return body
        time.sleep(0.5)
    raise AssertionError(f"job not done: {body}")


def test_process_round_trip(stack):
    client, _ = stack
    client.post("/upload", files=[("pdfs", ("a.pdf", b"%PDF", "application/pdf"))])

    body = client.post("/process").json()

    assert body["success"] is True
    assert body["results"][0]["filename"] == "a.pdf"


def test_bulk_job_is_spread_across_workers(stack):
    client, handled = stack
    files = [("pdfs", (f"doc{i}.pdf", b"%PDF", "application/pdf")) for i in range(12)]

    job_id = client.post("/jobs", files=files).json()["job_id"]
    body = wait_done(client, job_id)

    assert len(body["results"]) == 12
    assert all("structured_data" in r for r in body["results"])
    # prefetch=1 hands each worker one PDF at a time, so all three share the load.
    assert len(handled) == 3, handled


def test_migration_keeps_jobs_queued_on_the_old_classic_queue(monkeypatch):
    name = f"migration-test-{time.time_ns()}"
    for attr, value in [("JOBS_QUEUE", name), ("RETRY_QUEUE", f"{name}.retry"), ("DEAD_LETTER_QUEUE", f"{name}.dlq")]:
        monkeypatch.setattr(queues, attr, value)
    monkeypatch.setattr(migrate_queues, "JOBS_QUEUE", name)
    monkeypatch.setattr(migrate_queues, "HOLDING_QUEUE", f"{name}.migrating")

    connection = pika.BlockingConnection(pika.URLParameters(os.environ["RABBITMQ_URL"]))
    channel = connection.channel()
    channel.queue_declare(name, durable=True)  # the pre-quorum declaration
    channel.basic_publish("", name, b'{"job_id": "old"}')
    try:
        migrate_queues.main()
        migrate_queues.main()  # re-running is a no-op

        queues.declare(channel)  # would fail with PRECONDITION_FAILED on the old queue
        method, _, body = channel.basic_get(name, auto_ack=True)
        assert body == b'{"job_id": "old"}'
    finally:
        for queue in (name, f"{name}.retry", f"{name}.dlq", f"{name}.migrating"):
            channel.queue_delete(queue)
        connection.close()
