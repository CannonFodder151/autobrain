# AUT-1735: bump off vulnerable python:3.12-slim; pin base by digest.
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /ms-playwright \
    # AUT-1739 (CWE-250): run as non-root. Re-own Chromium's SUID sandbox
    # helper to root and set the setuid bit so Chromium can sandbox untrusted
    # content as the non-root user; browser.py falls back to --no-sandbox only
    # if a host can't initialise the sandbox.
    && find /ms-playwright -name chrome-sandbox -exec chown root:root {} \; \
    && find /ms-playwright -name chrome-sandbox -exec chmod 4755 {} \;
USER appuser

COPY main.py carsguide.py bikesguide.py sca.py browser.py ./

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
