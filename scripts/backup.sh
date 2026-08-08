#!/usr/bin/env bash
# Backup PostgreSQL and MinIO data to a tarball.
# Usage: ./scripts/backup.sh <output-dir>
set -euo pipefail

OUT="${1:?Usage: backup.sh <output-dir>}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

echo "==> Dumping PostgreSQL"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-autobrain}" "${POSTGRES_DB:-autobrain}" \
  > "$OUT/autobrain-db-$STAMP.sql"

echo "==> Backing up MinIO bucket"
BUCKET="${MINIO_BUCKET:-autobrain-assets}"
# minio-init container is gone (P1-1); the minio image bundles `mc`, so the
# mirror streams a tarball out of the running minio container — no extra container.
if docker compose exec -T minio sh -c \
    "mc alias set local http://localhost:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD >/dev/null 2>&1 && \
     mc mirror --overwrite local/$BUCKET /backup >/dev/null && \
     tar -czf - -C /backup ." \
    > "$OUT/autobrain-minio-$STAMP.tar.gz" 2>/dev/null; then
  echo "==> MinIO bucket mirrored to $OUT/autobrain-minio-$STAMP.tar.gz"
else
  rm -f "$OUT/autobrain-minio-$STAMP.tar.gz"
  echo " (minio backup skipped)"
fi

tar -czf "$OUT/autobrain-backup-$STAMP.tar.gz" -C "$OUT" "autobrain-db-$STAMP.sql" 2>/dev/null || true
echo "==> Backups written to $OUT/autobrain-backup-$STAMP.tar.gz"
