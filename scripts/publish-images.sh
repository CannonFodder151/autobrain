#!/usr/bin/env bash
# Build + push AutoBrain images to Docker Hub.
# Usage:
#   docker login                      # once, with your app.docker.com account
#   ./scripts/publish-images.sh [tag] # tag defaults to "latest"
# Frontend API/WS base URLs are read from .env (API_BASE_URL / WS_BASE_URL).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$REPO_ROOT/scripts/check-release.sh"
cd "$REPO_ROOT"

USER="${DOCKERHUB_USERNAME:?Set DOCKERHUB_USERNAME (e.g. DOCKERHUB_USERNAME=you ./scripts/publish-images.sh)}"
TAG="${1:-latest}"

API_BASE_URL="${API_BASE_URL:-http://localhost:8000/api/v1}"
WS_BASE_URL="${WS_BASE_URL:-ws://localhost:8000/ws}"
if [[ -f .env ]]; then
  API_BASE_URL="$(grep -E '^API_BASE_URL=' .env | tail -1 | cut -d= -f2- | tr -d '\r')"
  WS_BASE_URL="$(grep -E '^WS_BASE_URL=' .env | tail -1 | cut -d= -f2- | tr -d '\r')"
fi

echo "==> Building images as $USER/autobrain-*:$TAG"

echo "==> backend"
docker build -f docker/backend/Dockerfile -t "$USER/autobrain-backend:$TAG" .

echo "==> ai"
docker build -f docker/ai/Dockerfile -t "$USER/autobrain-ai:$TAG" ./ai

echo "==> frontend (API_BASE_URL=$API_BASE_URL WS_BASE_URL=$WS_BASE_URL)"
docker build -f docker/frontend/Dockerfile \
  --build-arg API_BASE_URL="$API_BASE_URL" \
  --build-arg WS_BASE_URL="$WS_BASE_URL" \
  -t "$USER/autobrain-frontend:$TAG" .

echo "==> Pushing"
docker push "$USER/autobrain-backend:$TAG"
docker push "$USER/autobrain-ai:$TAG"
docker push "$USER/autobrain-frontend:$TAG"

echo "==> Done. Deploy on server:"
echo "    DOCKERHUB_USERNAME=$USER IMAGE_TAG=$TAG docker compose -f docker-compose.prod.yml up -d"
