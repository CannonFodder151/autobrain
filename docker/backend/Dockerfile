# AutoBrain backend — production image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies layer (cached until requirements change)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# App source
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests

# Non-root user
RUN useradd -m -u 1000 autobrain && chown -R autobrain:autobrain /app
USER autobrain

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "python -m app.db.bootstrap && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
