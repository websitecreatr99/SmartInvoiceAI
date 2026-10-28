# InvoiceAI API: accepts uploads and hands PDFs to worker pods over RabbitMQ.
# OCR/LLM dependencies live in the worker image, so this one stays small.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app.py broker.py job_store.py metrics.py object_store.py queues.py ./

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p data storage \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
