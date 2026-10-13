# AutoBrain backend — unified production image (API + AI gateway + Celery worker + dongle-server + backup GUI).
# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
# AUT-2656: the previous digest (cc9dffa…) was a SINGLE-arch amd64 manifest
# (annotation bashbrew.arch: amd64). On the arm64 self-hosted runner, Docker
# pulled amd64 layers and every RUN step died with
# `exec /bin/sh: exec format error` (exit 255), so the arm64 build job never
# reached flutter/dart2js. Pin the MULTI-ARCH index tag+digest instead:
# 3.13.16-slim-trixie resolves to aarch64 on arm64 runners.
# AUT-6415: includes dongle-server and backup GUI for container consolidation.
FROM python:3.13.16-slim-trixie@sha256:6906dca82c0e83d5994bbf2e7fc33e6b63ce3e7f27c30eafd01dfabeb3c90bf3 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl minio-client git \
    && ln -s /usr/bin/minio-client /usr/local/bin/mc \
    && rm -rf /var/lib/apt/lists/*

# Backend dependencies
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

# AI gateway dependencies
COPY ai/requirements.txt /tmp/ai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/ai-requirements.txt

# Clone dongle-server (optional - public repo)
ARG DONGLE_SERVER_REPO=https://github.com/CannonFodder151/autobrain-dongle-server.git
ARG DONGLE_SERVER_REF=main
RUN git clone --depth 1 --branch ${DONGLE_SERVER_REF} ${DONGLE_SERVER_REPO} /tmp/dongle-server 2>/dev/null \
    && cd /tmp/dongle-server \
    && pip install --no-cache-dir -r requirements.txt 2>/dev/null \
    && cp -r dongle_server /app/dongle_server 2>/dev/null \
    && rm -rf /tmp/dongle-server \
    || echo "dongle-server repo not available, skipping"

# Clone backup GUI (optional - public repo to be created)
ARG BACKUP_REPO=https://github.com/CannonFodder151/autobrain-backup.git
ARG BACKUP_REF=main
RUN git clone --depth 1 --branch ${BACKUP_REF} ${BACKUP_REPO} /tmp/autobrain-backup 2>/dev/null \
    && cd /tmp/autobrain-backup \
    && pip install --no-cache-dir -r requirements.txt 2>/dev/null \
    && cp -r backup_gui /app/backup_gui 2>/dev/null \
    && rm -rf /tmp/autobrain-backup \
    || echo "backup repo not yet available, skipping"

# App source — backend + AI gateway + dongle-server + backup GUI share the same image
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

EXPOSE 8000 8001 8002 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Runs Celery worker+beat, AI gateway, dongle-server, and backup GUI alongside the API.
CMD ["sh", "-c", "/init-minio.sh && python -m app.db.bootstrap && (celery -A app.workers.celery_app:celery_app worker -B -l info --concurrency=2 &) && (uvicorn ai_app.main:app --host 0.0.0.0 --port 8001 &) && ([ -f /app/dongle_server/main.py ] && uvicorn dongle_server.main:app --host 0.0.0.0 --port 8002 &) && ([ -f /app/backup_gui/main.py ] && uvicorn backup_gui.main:app --host 0.0.0.0 --port 8080 &) && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]