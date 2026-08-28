FROM python:3.12-slim

# CWE-250: run the container (and the Playwright/Chromium scraper) as a non-root
# user. A browser exploit can no longer escalate to container root.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --shell /usr/sbin/nologin --create-home appuser

WORKDIR /app

# Keep Playwright browsers in a world-readable path so the non-root user can use
# them (the default /root/.cache is not traversable by a non-root user).
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/ms-playwright
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_ROOT_USER_ACTION=ignore

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY main.py carsguide.py bikesguide.py sca.py browser.py ./

RUN chown -R appuser:appuser /app /usr/local/share/ms-playwright

# Let Chromium sandbox as the non-root user: the SUID sandbox helper must be
# root-owned and setuid so Chromium can drop privileges after launch.
RUN SB=$(find /usr/local/share/ms-playwright -name chrome-sandbox -type f | head -n1); \
    if [ -n "$SB" ]; then chown root:root "$SB" && chmod 4755 "$SB"; fi

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
