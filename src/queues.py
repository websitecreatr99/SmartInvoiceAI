"""Queue topology. The API, worker and smoke test must all declare queues through
`declare()`: RabbitMQ rejects a redeclare with different arguments (PRECONDITION_FAILED).

invoice.jobs        quorum queue. A message handed out more than MAX_REDELIVERIES + 1 times
                    (it crashed or hung every pod that took it) is dead-lettered to the DLQ.
invoice.jobs.retry  jobs that hit a temporary error (Gemini 429/5xx, storage outage) wait
                    RETRY_DELAY_SECONDS here, then flow back into invoice.jobs.
invoice.jobs.dlq    poison messages, kept for inspection.
invoice.results     one result per job.
"""
import os

JOBS_QUEUE = os.getenv("JOBS_QUEUE", "invoice.jobs")
RESULTS_QUEUE = os.getenv("RESULTS_QUEUE", "invoice.results")
RETRY_QUEUE = os.getenv("RETRY_QUEUE", f"{JOBS_QUEUE}.retry")
DEAD_LETTER_QUEUE = os.getenv("DEAD_LETTER_QUEUE", f"{JOBS_QUEUE}.dlq")
RETRY_DELAY_SECONDS = int(os.getenv("RETRY_DELAY_SECONDS", "30"))
# Deliveries a message may lose (pod crash, OOM, hang) before the worker gives up on it.
MAX_REDELIVERIES = int(os.getenv("MAX_REDELIVERIES", "2"))


def declare(channel):
    channel.queue_declare(queue=DEAD_LETTER_QUEUE, durable=True, arguments={"x-queue-type": "quorum"})
    channel.queue_declare(
        queue=JOBS_QUEUE,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            # Backstop: the worker reports and parks a poison message itself one delivery earlier.
            "x-delivery-limit": MAX_REDELIVERIES + 1,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": DEAD_LETTER_QUEUE,
        },
    )
    channel.queue_declare(
        queue=RETRY_QUEUE,
        durable=True,
        arguments={
            "x-message-ttl": RETRY_DELAY_SECONDS * 1000,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": JOBS_QUEUE,
        },
    )
    channel.queue_declare(queue=RESULTS_QUEUE, durable=True)


def prior_deliveries(headers) -> int:
    """Times RabbitMQ already handed this message out without an ack (quorum queues track this)."""
    headers = headers or {}
    # x-delivery-count up to RabbitMQ 3.13; 4.x counts every return in x-acquired-count.
    counts = [headers.get("x-delivery-count"), headers.get("x-acquired-count")]
    return max((c for c in counts if isinstance(c, int)), default=0)
