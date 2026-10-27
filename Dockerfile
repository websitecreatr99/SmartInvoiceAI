# InvoiceAI backend image, shared by the API and the Celery workers.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# poppler-utils: pdf2image; libgl1/libglib2.0-0: OpenCV; libgomp1: PaddlePaddle
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txt ends with `-e .`, so setup.py and the package must be present first.
COPY requirements.txt setup.py ./
COPY src ./src
RUN pip install -r requirements.txt paddlepaddle==3.2.0

COPY app.py celery_app.py jobs.py tasks.py ocr_pipeline.py ./

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p storage logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health')"

# Same image runs the workers: override the command with `celery -A celery_app worker`.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 5000 --workers ${UVICORN_WORKERS:-2}"]
