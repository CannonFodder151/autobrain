#!/bin/bash
set -u

# AUT-1242-C3: run AI gateway (:8001) and market-data scraper (:8000)
# as two uvicorn processes in one container.

echo "[ai] starting market-data scraper on :8000"
(cd /app/market-data && exec uvicorn main:app --host 0.0.0.0 --port 8000) &
MD_PID=$!

echo "[ai] starting AI gateway on :8001"
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
AI_PID=$!

trap 'kill $MD_PID $AI_PID 2>/dev/null || true' INT TERM

# Whichever process dies first tears the container down so Docker restarts it.
wait -n
rc=$?
kill $MD_PID $AI_PID 2>/dev/null || true
wait 2>/dev/null || true
exit $rc