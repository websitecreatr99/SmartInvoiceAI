"""RabbitMQ plumbing between the API and the worker pods (worker branch).

invoice.jobs     API -> workers, one message per document (queues.py has the full topology)
invoice.results  workers -> API, one message per processed document
"""
import json
import logging
import os
import threading
from typing import Callable, List

import pika
from pika.exceptions import AMQPError

from queues import JOBS_QUEUE, RESULTS_QUEUE, declare

logger = logging.getLogger("broker")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")


def _params() -> pika.URLParameters:
    params = pika.URLParameters(RABBITMQ_URL)
    params.heartbeat = 60
    params.blocked_connection_timeout = 30
    return params


def publish_jobs(messages: List[dict]):
    """Publish job messages durably; raises AMQPError if the broker doesn't confirm them."""
    connection = pika.BlockingConnection(_params())
    try:
        channel = connection.channel()
        declare(channel)
        channel.confirm_delivery()
        for message in messages:
            channel.basic_publish(
                exchange="",
                routing_key=JOBS_QUEUE,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent, content_type="application/json"
                ),
                mandatory=True,
            )
    finally:
        connection.close()


class ResultConsumer(threading.Thread):
    """Background thread that feeds worker results to `on_result`, reconnecting if the broker drops."""

    def __init__(self, on_result: Callable[[dict], bool]):
        super().__init__(name="result-consumer", daemon=True)
        self.on_result = on_result
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                connection = pika.BlockingConnection(_params())
                channel = connection.channel()
                declare(channel)
                channel.basic_qos(prefetch_count=50)
                logger.info(f"Consuming results from {RESULTS_QUEUE}")
                for method, _, body in channel.consume(RESULTS_QUEUE, inactivity_timeout=1):
                    if self._stop_event.is_set():
                        break
                    if method is None:
                        continue
                    try:
                        result = json.loads(body)
                        # Log the job id only: result bodies hold extracted customer data.
                        if not self.on_result(result):
                            logger.warning(f"Dropped result for unknown job {result.get('job_id')!r}")
                    except Exception:
                        logger.exception("Failed to store result; dropping it")
                    channel.basic_ack(method.delivery_tag)
                channel.cancel()
                connection.close()
            except AMQPError as e:
                logger.warning(f"RabbitMQ unavailable ({e!r}); retrying in 5s")
                self._stop_event.wait(5)
