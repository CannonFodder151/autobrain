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

# AUT-601: this image runs BOTH the worker and the beat scheduler. `celery
# inspect ping` only proves a worker answers on the control bus, so it does not
# prove the embedded beat scheduler is healthy — and under AI-task load it also
# false-negatives for the worker itself. Prior to AUT-1242/C1 the Portainer
# stacks ran a separate `beat` service from this image, so the check is
# command-aware: the beat branch validates that the PersistentScheduler keeps
# writing `celerybeat-schedule` (stale file = wedged scheduler loop, e.g. the
# 100% CPU busy-loop from AUT-601). Hosted now embeds beat via `worker -B`
# (AUT-1242/C1), so the branch only fires for legacy/standalone beat runs.
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD sh -c 'c=$(tr "\0" " " < /proc/1/cmdline); case "$c" in *" beat "*) [ -f celerybeat-schedule ] || exit 1; [ -z "$(find celerybeat-schedule -mmin -30 2>/dev/null)" ] && exit 1; exit 0 ;; *) celery -A app.workers.celery_app:celery_app inspect ping -t 8 -d "celery@$(hostname)" ;; esac'

CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "-l", "info", "--concurrency=2"]
