#!/bin/sh
set -e

ENDPOINT="${MINIO_ENDPOINT:-minio:9000}"
ACCESS_KEY="${MINIO_ACCESS_KEY:?MINIO_ACCESS_KEY must be set}"
SECRET_KEY="${MINIO_SECRET_KEY:?MINIO_SECRET_KEY must be set}"
BUCKET="${MINIO_BUCKET:-autobrain-assets}"

echo "[init-minio] Waiting for MinIO at $ENDPOINT ..."
until mc alias set local "http://$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" 2>/dev/null; do
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
