# AutoBrain AI image: AI gateway (:8001) + market-data scraper (:8000)
# AUT-1242-C3: market-data merged into this image to drop a container.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tesseract for local OCR fallback
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY ai/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Playwright chromium for market-data scraper (AUT-1242-C3)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY ai/app ./app
COPY market-data ./market-data
COPY docker/ai/entrypoint.sh /entrypoint.sh
# AUT-1533: *_FILE secret loader, sourced by /entrypoint.sh.
COPY docker/lib-load-secrets.sh /usr/local/bin/lib-load-secrets.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/lib-load-secrets.sh

RUN useradd -m -u 1000 autobrain \
    && chown -R autobrain:autobrain /app \
    && mkdir -p /ms-playwright && chown -R autobrain:autobrain /ms-playwright
USER autobrain

EXPOSE 8000 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8001/health && curl -fsS http://localhost:8000/health || exit 1

CMD ["/entrypoint.sh"]
