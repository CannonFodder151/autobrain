# AutoBrain Celery worker — production image (reuses backend image)
# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
# AUT-2067: bump to latest 3.13-slim digest to clear HIGH CVEs (libffi/libssl/libsecret).
FROM python:3.13-slim@sha256:cc9dffa47c8294ba9bb795a8dfaeb7b76f2b30acade2c52a461a2999d127eb00

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
# false-negatives on the control bus). The check is command-aware:
# - When PID 1 embeds beat (`worker -B` or separate `beat`), it validates that
#   the PersistentScheduler keeps writing `celerybeat-schedule` (stale file =
#   wedged scheduler loop, e.g. the 100% CPU busy-loop from AUT-601).
# - Worker-only: scan /proc for the celery worker process (deterministic;
#   no AMQP round-trip, no pgrep dependency, no nested `$()` that breaks
#   busybox/dash). AUT-1878: `inspect ping` exits 1 on a healthy worker in the
#   hosted stack — process check is more reliable.
#
# AUT-2056: use `bash -c` (present in python:3.13-slim Debian base) to avoid
# `sh` parsing bugs with `$()` inside `[ ... ]`. Command uses `grep -q` on
# /proc/*/comm and cmdline — pure POSIX, no nested substitutions in tests.
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s --retries=3 \
    CMD bash -c 'c=$(tr "\0" " " </proc/1/cmdline); case "$c" in *-B*|*beat*) [ -f celerybeat-schedule ] && find celerybeat-schedule -mmin -30 2>/dev/null | grep -q . || exit 1 ;; *) for d in /proc/[0-9]*; do [ -r "$d/comm" ] || continue; cat "$d/comm" 2>/dev/null | grep -q "^celery$" || continue; tr "\0" " " < "$d/cmdline" 2>/dev/null | grep -q "celery.*worker" && exit 0; done; exit 1 ;; esac'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "-l", "info", "--concurrency=2"]
