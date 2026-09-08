# AutoBrain AI image: AI gateway (:8001) + market-data scraper (:8000)
# AUT-1242-C3: market-data merged into this image to drop a container.
# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS base

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
# AUT-1739 (CWE-250) + AUT-2258: the image already runs as non-root `autobrain`.
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
    CMD curl -fsS http://localhost:8001/health && curl -fsS http://localhost:8000/health || exit 1

CMD ["/entrypoint.sh"]
