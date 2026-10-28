# InvoiceAI worker: consumes PDFs from RabbitMQ and runs OCR + LLM extraction.
FROM python:3.11-slim

# OPENCV_IO_MAX_IMAGE_PIXELS: refuse images over 100 MP instead of allocating gigabytes for one upload.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ALIVE_FILE=/tmp/worker-alive \
    OPENCV_IO_MAX_IMAGE_PIXELS=100000000

# poppler-utils: pdf2image; libgl1/libglib2.0-0: OpenCV; libgomp1: PaddlePaddle
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txt ends with `-e .`, so setup.py and the package must be present first.
COPY requirements.txt setup.py ./
COPY src ./src
RUN pip install -r requirements.txt

COPY ocr_pipeline.py worker.py ./

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p logs \
    && chown -R appuser:appuser /app
USER appuser

# Prometheus metrics on 9100. Liveness: the consumer touches ALIVE_FILE every 15s while connected to RabbitMQ.
EXPOSE 9100

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, time, sys; sys.exit(time.time() - os.path.getmtime(os.environ['ALIVE_FILE']) > 60)"

CMD ["python", "worker.py"]
