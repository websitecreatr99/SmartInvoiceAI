"""One-off: replace a classic invoice.jobs (API/worker versions before the quorum queue)
with the queues that queues.declare() expects, without losing queued jobs.

RabbitMQ can't change a queue's type in place, so queued jobs are parked in a holding
queue while invoice.jobs is recreated, then moved back. Old jobs carry inline file_b64,
which the new worker still accepts.

1. Scale the workers to 0 (they consume invoice.jobs). The API answers 503 to new jobs
   from here until step 3.
2. RABBITMQ_URL=amqp://... python scripts/migrate_queues.py
3. Deploy the new API and worker images.

Safe to re-run: it does nothing once the queues match.
"""
import os
import sys

import pika
from pika.exceptions import ChannelClosedByBroker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from queues import JOBS_QUEUE, declare  # noqa: E402

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
HOLDING_QUEUE = f"{JOBS_QUEUE}.migrating"


def move(channel, source: str, target: str) -> int:
    """Move every message from source to target; each is acked only after the broker confirms the copy."""
    moved = 0
    while True:
        method, properties, body = channel.basic_get(source)
        if method is None:
            return moved
        channel.basic_publish("", target, body, properties, mandatory=True)
        channel.basic_ack(method.delivery_tag)
        moved += 1


def main():
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    try:
        try:
            declare(connection.channel())
            print("Queues already match queues.py; nothing to do.")
            return
        except ChannelClosedByBroker as e:
            if e.reply_code != 406:  # PRECONDITION_FAILED: exists with other arguments
                raise
            print(f"{JOBS_QUEUE} has old arguments; migrating")

        channel = connection.channel()
        channel.confirm_delivery()
        consumers = channel.queue_declare(JOBS_QUEUE, passive=True).method.consumer_count
        if consumers:
            sys.exit(f"{consumers} consumer(s) still attached to {JOBS_QUEUE}; scale the workers to 0 first")

        channel.queue_declare(HOLDING_QUEUE, durable=True)
        print(f"Parked {move(channel, JOBS_QUEUE, HOLDING_QUEUE)} queued job(s) in {HOLDING_QUEUE}")
        channel.queue_delete(JOBS_QUEUE, if_empty=True)
        declare(channel)
        print(f"Moved {move(channel, HOLDING_QUEUE, JOBS_QUEUE)} job(s) into the new {JOBS_QUEUE}")
        channel.queue_delete(HOLDING_QUEUE, if_empty=True)
        print("Done. Deploy the new API and worker.")
    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    main()
