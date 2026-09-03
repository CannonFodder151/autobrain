# AutoBrain backend — unified production image (API + AI gateway + Celery worker).
# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
# AUT-2067: bump to latest 3.13-slim digest to clear HIGH CVEs (libffi/libssl/libsecret).
FROM python:3.13-slim@sha256:cc9dffa47c8294ba9bb795a8dfaeb7b76f2b30acade2c52a461a2999d127eb00 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl minio-client \
    && ln -s /usr/bin/minio-client /usr/local/bin/mc \
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
COPY ai/app ./ai_app
COPY ai/requirements.txt ./ai_requirements.txt

# Non-root user
RUN useradd -m -u 1000 autobrain && chown -R autobrain:autobrain /app

# MinIO init entrypoint (before dropping privileges)
COPY scripts/init-minio.sh /init-minio.sh
RUN chmod +x /init-minio.sh

# AUT-1533: *_FILE secret loader wraps the CMD so credentials arrive via
# bind-mounted files instead of plain env vars.
COPY docker/entrypoint.sh docker/lib-load-secrets.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/lib-load-secrets.sh

USER autobrain

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Runs Celery worker+beat alongside the API (single-container backend).
CMD ["sh", "-c", "/init-minio.sh && python -m app.db.bootstrap && (celery -A app.workers.celery_app:celery_app worker -B -l info --concurrency=2 &) && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
