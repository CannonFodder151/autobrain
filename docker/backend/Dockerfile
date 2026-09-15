# AutoBrain backend — unified production image (API + AI gateway + market-data + Celery worker).
# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
# AUT-2656: the previous digest (cc9dffa…) was a SINGLE-arch amd64 manifest
# (annotation bashbrew.arch: amd64). On the arm64 self-hosted runner, Docker
# pulled amd64 layers and every RUN step died with
# `exec /bin/sh: exec format error` (exit 255), so the arm64 build job never
# reached flutter/dart2js. Pin the MULTI-ARCH index tag+digest instead:
# 3.13.15-slim-trixie resolves to aarch64 on arm64 runners.
FROM python:3.13.15-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tesseract for local OCR fallback (fuel-ocr, odometer modules)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl minio-client tesseract-ocr tesseract-ocr-eng \
    && ln -s /usr/bin/minio-client /usr/local/bin/mc \
    && rm -rf /var/lib/apt/lists/*

# Backend dependencies
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

# AI gateway + market-data dependencies (playwright, playwright-stealth for scraping)
COPY ai/requirements.txt /tmp/ai-requirements.txt
RUN pip install --no-cache-dir -r /tmp/ai-requirements.txt

# Playwright chromium for market-data scraper
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# App source — backend + AI gateway + market-data share the same image
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
# AUT-2826: AI gateway code uses `from app.X` imports which collide with the
# backend's `app` package. Isolate the AI gateway in its own directory so
# `from app.X` resolves to the AI gateway code when uvicorn starts from
# that directory.
COPY ai/app /app/ai_pkg/app
COPY ai/requirements.txt ./ai_requirements.txt
COPY market-data ./market-data

# Non-root user
RUN useradd -m -u 1000 autobrain \
    && chown -R autobrain:autobrain /app \
    && mkdir -p /ms-playwright \
    && chown -R autobrain:autobrain /ms-playwright

# MinIO init entrypoint (before dropping privileges)
COPY scripts/init-minio.sh /init-minio.sh
RUN chmod +x /init-minio.sh

# AUT-1533: *_FILE secret loader wraps the CMD so credentials arrive via
# bind-mounted files instead of plain env vars.
COPY docker/entrypoint.sh docker/lib-load-secrets.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/lib-load-secrets.sh

# AUT-1739 (CWE-250) + AUT-2258: run as non-root `autobrain`.
# Re-own Chromium's SUID sandbox helper to root + setuid so the market-data
# scraper can sandbox untrusted third-party content as that non-root user; the
# scraper falls back to --no-sandbox only if a host can't initialise the sandbox.
# Run as the FINAL root RUN (not chained with the autobrain chowns above) so
# the chown/chmod cannot be masked by any later layer change. AUT-2258
# root-cause: the previous chained RUN with `&&` could be invalidated by any
# upstream layer change, leaving chrome-sandbox autobrain:autobrain 0755 at
# runtime (CTO verification 2026-09-03). This RUN runs as root (USER switched
# back to root) so chown root:root succeeds regardless of build-host uid.
# AUT-2582 fix: Playwright 1.62+ ships chrome_sandbox (underscore); also match
# chrome-sandbox (hyphen) for older Playwright versions so the SUID sandbox
# helper is always root-owned + setuid regardless of naming convention.
USER root
RUN set -eux; \
    sb_count=0; \
    for sb in $(find /ms-playwright -type f \( -name chrome-sandbox -o -name chrome_sandbox \)); do \
        chown root:root "$sb"; \
        chmod 4755 "$sb"; \
        sb_count=$((sb_count+1)); \
    done; \
    if [ "$sb_count" -gt 0 ]; then \
        echo "AUT-1739: re-SUID $sb_count chrome-sandbox binary(ies) under /ms-playwright"; \
    else \
        echo "AUT-1739: no chrome-sandbox found under /ms-playwright (Playwright 1.62+ kernel sandbox)" >&2; \
        ls -la /ms-playwright >&2; \
    fi
USER autobrain

EXPOSE 8000 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health && curl -fsS http://localhost:8001/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Runs Celery worker+beat and AI gateway (:8001) alongside the API (single-container backend).
CMD ["sh", "-c", "/init-minio.sh && python -m app.db.bootstrap && (celery -A app.workers.celery_app:celery_app worker -B -l info --concurrency=2 &) && (cd /app/ai_pkg && uvicorn app.main:app --host 0.0.0.0 --port 8001 &) && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]