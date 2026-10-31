# InvoiceAI backend in one Hugging Face Space: RabbitMQ + API (fastapi branch) + worker (worker branch).
# Spaces block outbound traffic to anything but ports 80/443/8080, so a hosted broker like CloudAMQP
# (5671) is unreachable; RabbitMQ runs in this container instead. deploy.sh fills api/ and worker/.
FROM python:3.11-slim-bookworm

# rabbitmq-server: the broker; poppler-utils: pdf2image; libgl1/libglib2.0-0: OpenCV; libgomp1: PaddlePaddle
RUN apt-get update \
    && apt-get install -y --no-install-recommends rabbitmq-server poppler-utils libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as uid 1000.
RUN useradd --create-home --uid 1000 user
ENV HOME=/home/user \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OPENCV_IO_MAX_IMAGE_PIXELS=100000000 \
    RABBITMQ_MNESIA_BASE=/home/user/rabbitmq/mnesia \
    RABBITMQ_LOG_BASE=/home/user/rabbitmq/log \
    RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F \
    STORAGE_DIR=/home/user/storage \
    ALIVE_FILE=/tmp/worker-alive

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
COPY worker/requirements.txt worker/setup.py worker/
COPY worker/src worker/src
RUN pip install supervisor==4.2.5 -r api/requirements.txt \
    && cd worker && pip install -r requirements.txt

COPY --chown=user . .
RUN mkdir -p worker/logs && chown -R user:user /app
USER user

EXPOSE 5000
CMD ["supervisord", "-c", "/app/supervisord.conf"]
