#!/bin/sh
# Best-effort MinIO bucket initialization — never block backend startup (AUT-1786).
ENDPOINT="${MINIO_ENDPOINT:-minio:9000}"
BUCKET="${MINIO_BUCKET:-autobrain-assets}"

if [ -z "${MINIO_ACCESS_KEY:-}" ] || [ -z "${MINIO_SECRET_KEY:-}" ]; then
  echo "[init-minio] MINIO_ACCESS_KEY / MINIO_SECRET_KEY not set; skipping bucket init." >&2
  exit 0
fi

set -e

ACCESS_KEY="$MINIO_ACCESS_KEY"
SECRET_KEY="$MINIO_SECRET_KEY"

echo "[init-minio] Waiting for MinIO at $ENDPOINT ..."
# Bounded wait: give MinIO 60s before giving up (prevents infinite hang if MinIO is down).
TRIES=0
until mc alias set local "http://$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" 2>/dev/null; do
  TRIES=$((TRIES + 1))
  if [ "$TRIES" -ge 30 ]; then
    echo "[init-minio] MinIO not reachable after ${TRIES} attempts; skipping." >&2
    exit 0
  fi
  sleep 2
done

echo "[init-minio] Connected."

if mc ls "local/$BUCKET" >/dev/null 2>&1; then
  echo "[init-minio] Bucket '$BUCKET' already exists."
else
  echo "[init-minio] Creating bucket '$BUCKET' ..."
  mc mb "local/$BUCKET"
fi

echo "[init-minio] Ensuring bucket '$BUCKET' is private (no anonymous access) ..."
mc anonymous set none "local/$BUCKET"

echo "[init-minio] Done."
