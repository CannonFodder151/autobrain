# AutoBrain Celery worker — production image (reuses backend image)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

RUN useradd -m -u 1000 autobrain && chown -R autobrain:autobrain /app
USER autobrain

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["celery", "inspect", "ping"]

CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "-l", "info", "--concurrency=2"]
