ARG BASE_IMAGE=autobrain-backend:latest
FROM ${BASE_IMAGE}

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["celery", "inspect", "ping"]

CMD ["celery", "-A", "app.workers.celery_app:celery_app", "worker", "-B", "-l", "info", "--concurrency=2"]
