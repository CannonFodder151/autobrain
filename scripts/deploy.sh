#!/usr/bin/env bash
set -euo pipefail

# Nightly hosted deploy to EP5 (152.69.188.133)
# Window: 03:00-04:00 AEST (17:00-18:00 UTC)
# Stack 122 - inline, digest-pinned
# Excludes: demo, default stacks

HOST="${HOST:-152.69.188.133}"
STACK="${STACK:-122}"
STACK_DIGEST="${STACK_DIGEST:-sha256:latest}"
PORT="${PORT:-8000}"

echo "=== Nightly Hosted Deploy ==="
echo "Target: EP5 (${HOST}:${PORT})"
echo "Stack: ${STACK} (digest-pinned: ${STACK_DIGEST})"
echo "Excluding: demo, default stacks"

# 1. Build image with digest pin
echo "Building image..."
docker build -t "vehicle-health:${STACK}@${STACK_DIGEST}" .

# 2. Tag and push to registry
echo "Pushing to registry..."
docker tag "vehicle-health:${STACK}@${STACK_DIGEST}" "${HOST}:5000/vehicle-health:${STACK}@${STACK_DIGEST}"
docker push "${HOST}:5000/vehicle-health:${STACK}@${STACK_DIGEST}"

# 3. Deploy to hosted (replace running container)
echo "Deploying to EP5..."
docker stop "vehicle-health-${STACK}" || true
docker rm "vehicle-health-${STACK}" || true
docker run -d \
  --name "vehicle-health-${STACK}" \
  --restart unless-stopped \
  -p "${PORT}:8000" \
  "${HOST}:5000/vehicle-health:${STACK}@${STACK_DIGEST}"

# 4. Health check
echo "Running health check..."
sleep 5
curl -f -s "http://${HOST}:${PORT}/health" || { echo "Health check FAILED"; exit 1; }
curl -f -s "http://${HOST}:${PORT}/api" || { echo "API check FAILED"; exit 1; }

echo "=== Deploy complete ==="