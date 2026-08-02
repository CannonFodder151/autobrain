# AutoBrain AI inference gateway — production image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tesseract for local OCR fallback
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app ./app
COPY tests ./tests

RUN useradd -m -u 1000 autobrain && chown -R autobrain:autobrain /app
USER autobrain

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8001/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
