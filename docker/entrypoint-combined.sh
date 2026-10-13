#!/bin/sh
# Combined entrypoint for backend + dongle-server + backup GUI
# Loads secrets then starts all services in the backend container.

. /usr/local/bin/lib-load-secrets.sh

# Start MinIO initialization (non-blocking)
/init-minio.sh &

# Run database migrations and bootstrap
alembic upgrade head
python -m app.db.bootstrap

# Start Celery worker + beat in background
celery -A app.workers.celery_app:celery_app worker -B -l info --concurrency=2 &

# Start AI gateway on port 8001
uvicorn ai_app.main:app --host 0.0.0.0 --port 8001 &

# Start dongle-server on port 8002 (if code is available)
if [ -f /app/dongle_server/main.py ]; then
    uvicorn dongle_server.main:app --host 0.0.0.0 --port 8002 &
fi

# Start backup GUI on port 8080 (if code is available)
if [ -f /app/backup_gui/main.py ]; then
    uvicorn backup_gui.main:app --host 0.0.0.0 --port 8080 &
fi

# Start main backend API on port 8000 (foreground)
exec uvicorn app.main:app --host 0.0.0.0 --port 8000