#!/usr/bin/env bash
# Deploy AutoBrain to a Linux host over SSH using docker compose.
# Usage: ./scripts/deploy.sh <user@host>
set -euo pipefail

HOST="${1:?Usage: deploy.sh <user@host>}"
REMOTE_DIR="~/autobrain"
SSH_ARGS=${SSH_ARGS:-""}
HOST_IP="${HOST#*@}"

echo "==> Syncing project to $HOST:$REMOTE_DIR"
ssh $SSH_ARGS "$HOST" "mkdir -p $REMOTE_DIR"

# rsync not required; use tar over ssh for portability
tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    --exclude='backend/__pycache__' -czf - . |
  ssh $SSH_ARGS "$HOST" "tar -xzf - -C $REMOTE_DIR"

echo "==> Ensuring .env exists on remote"
ssh $SSH_ARGS "$HOST" "test -f $REMOTE_DIR/.env || cp $REMOTE_DIR/.env.example $REMOTE_DIR/.env"

echo "==> Pointing frontend build args at this host if still on placeholders"
ssh $SSH_ARGS "$HOST" "cd $REMOTE_DIR && sed -i 's|^API_BASE_URL=.*|API_BASE_URL=http://$HOST_IP/api/v1|; s|^WS_BASE_URL=.*|WS_BASE_URL=ws://$HOST_IP/ws|' .env"

echo "==> Building and starting production stack (docker snap can only read ~/, hence REMOTE_DIR)"
ssh $SSH_ARGS "$HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml up -d --build"

echo "==> Checking health"
sleep 10
curl -fsS "http://$HOST/health" && echo " -> healthy" || echo " -> health check failed (check docker logs)"
