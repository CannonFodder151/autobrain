# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /ms-playwright
# AUT-1739 (CWE-250) + AUT-2258: run as non-root. Re-own Chromium's SUID
# sandbox helper to root + setuid so Chromium can sandbox untrusted content
# as the non-root user; browser.py falls back to --no-sandbox only if a host
# can't initialise the sandbox. Run as a SEPARATE final RUN so the chown
# cannot be masked by any later layer. AUT-2258 root-cause: the previous
# chained RUN could be invalidated by any upstream layer change, leaving
# chrome-sandbox appuser:appuser 0755 at runtime (CTO verification 2026-09-03).
# This RUN runs as root (USER switched back to root) so chown root:root
# succeeds regardless of build-host uid.
# AUT-2518: Playwright 1234+ (Chrome for Testing) ships no chrome-sandbox —
# Chromium uses user namespaces in headless mode. Relax to warn-and-continue
# when zero matches so the build does not abort on the new layout. Match both
# chrome-sandbox (hyphen) and chrome_sandbox (underscore) for older Playwright.
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
        echo "AUT-1739/AUT-2518: no chrome-sandbox found under /ms-playwright (Playwright 1234+ kernel sandbox)" >&2; \
        ls -la /ms-playwright >&2; \
    fi
USER appuser

COPY main.py carsguide.py bikesguide.py sca.py browser.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
