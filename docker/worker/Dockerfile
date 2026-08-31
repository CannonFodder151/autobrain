# AutoBrain Celery worker — production image (reuses backend image)
# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f

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

# AUT-1533: *_FILE secret loader wraps the CMD.
COPY docker/entrypoint.sh docker/lib-load-secrets.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/lib-load-secrets.sh

USER autobrain

# AUT-601 / AUT-1286 / AUT-1878: this image runs BOTH the worker and the beat scheduler.
# The healthcheck verifies the beat scheduler (via celerybeat-schedule freshness)
# AND that a celery worker process is alive. Avoids `inspect ping` false negatives.
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD sh -c '[ -f celerybeat-schedule ] || exit 1; [ -z "$(find celerybeat-schedule -mmin -30 2>/dev/null)" ] && exit 1; pgrep -f "celery.*worker" >/dev/null || exit 1; exit 0'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "-l", "info", "--concurrency=2"]
