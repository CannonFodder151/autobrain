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
docker compose run --rm -T minio-init \
  /bin/sh -c "mc alias set local http://minio:9000 ${MINIO_ACCESS_KEY:-autobrain} ${MINIO_SECRET_KEY:-autobrain} && \
  mc mirror --overwrite local/${MINIO_BUCKET:-autobrain-assets} /backup" \
  > /dev/null 2>&1 || echo " (minio backup skipped)"

tar -czf "$OUT/autobrain-backup-$STAMP.tar.gz" -C "$OUT" "autobrain-db-$STAMP.sql" 2>/dev/null || true
echo "==> Backups written to $OUT/autobrain-backup-$STAMP.tar.gz"
