"""Prometheus metrics for the API, scraped from /metrics by the tracking stack."""
from prometheus_client import Counter, Histogram

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600)
JOB_BUCKETS = (1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800)

REQUESTS = Counter("invoiceai_api_requests_total", "HTTP requests", ["method", "route", "status"])
REQUEST_SECONDS = Histogram(
    "invoiceai_api_request_duration_seconds", "HTTP request latency", ["method", "route"], buckets=LATENCY_BUCKETS
)
JOBS_SUBMITTED = Counter("invoiceai_api_jobs_submitted_total", "Jobs queued for the workers", ["endpoint"])
PDFS_SUBMITTED = Counter("invoiceai_api_pdfs_submitted_total", "PDFs published to the jobs queue")
PUBLISH_FAILURES = Counter("invoiceai_api_publish_failures_total", "Jobs rejected because RabbitMQ was unavailable")
RESULTS = Counter("invoiceai_api_results_received_total", "Worker results received", ["status"])
JOB_SECONDS = Histogram(
    "invoiceai_api_job_duration_seconds", "Time from job submission until its last PDF result", buckets=JOB_BUCKETS
)
