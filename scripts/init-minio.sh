#!/bin/sh
set -e

ENDPOINT="${MINIO_ENDPOINT:-minio:9000}"
ACCESS_KEY="${MINIO_ACCESS_KEY:-autobrain}"
SECRET_KEY="${MINIO_SECRET_KEY:-autobrain}"
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

POLICY=$(mc anonymous get "local/$BUCKET" 2>/dev/null || true)
if echo "$POLICY" | grep -q "download"; then
  echo "[init-minio] Bucket already has download policy."
else
  echo "[init-minio] Setting download policy on '$BUCKET' ..."
  mc anonymous set download "local/$BUCKET"
fi

echo "[init-minio] Done."
