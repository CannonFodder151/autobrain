# AutoBrain Shop backend image (API + AI gateway + Celery worker).
FROM python:3.13.5-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl minio-client \
    && ln -s /usr/bin/minio-client /usr/local/bin/mc \
    && rm -rf /var/lib/apt/lists/*

# Dependencies
COPY shop/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# App source
COPY shop/app ./app
COPY shop/alembic ./alembic
COPY shop/alembic.ini ./

# Non-root user
RUN useradd -m -u 1000 shop && chown -R shop:shop /app

USER shop

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]