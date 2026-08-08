# AutoBrain backend — unified production image (API + AI gateway + Celery worker).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl minio-client \
    && rm -rf /var/lib/apt/lists/*

# Backend dependencies
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

# AI gateway dependencies
COPY ai/requirements.txt /tmp/ai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/ai-requirements.txt

# App source — backend + AI gateway share the same image
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY backend/tests ./tests
COPY ai/app ./ai_app
COPY ai/requirements.txt ./ai_requirements.txt

# Non-root user
RUN useradd -m -u 1000 autobrain && chown -R autobrain:autobrain /app
USER autobrain

# MinIO init entrypoint
COPY scripts/init-minio.sh /init-minio.sh
RUN chmod +x /init-minio.sh

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "/init-minio.sh && python -m app.db.bootstrap && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
