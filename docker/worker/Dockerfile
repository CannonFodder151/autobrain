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

# AUT-601 / AUT-1286 / AUT-1878 / AUT-2056: this image runs BOTH the worker and
# the beat scheduler. `celery inspect ping` is unreliable (fails under load,
# false-negatives on the control bus). The check is deterministic: scan /proc
# for a process whose `comm` is `celery` and whose `cmdline` contains `worker`.
# This covers both `celery worker` and `celery worker -B` cases — no AMQP
# round-trip, no nested `$()`, no busybox/dash compatibility issues.
# AUT-1878 root cause: the earlier beat branch relied on `find -mmin -30`
# against `celerybeat-schedule`, but PersistentScheduler only writes that file
# on shutdown/checkpoint — not on every tick — so it false-negatives a
# perfectly alive worker+beat process. Unify to the PID scan for both modes.
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD bash -c 'for d in /proc/[0-9]*; do [ -r "$d/comm" ] || continue; cat "$d/comm" 2>/dev/null | grep -q "^celery$" || continue; tr "\0" " " < "$d/cmdline" 2>/dev/null | grep -q "celery.*worker" && exit 0; done; exit 1'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "-l", "info", "--concurrency=2"]
