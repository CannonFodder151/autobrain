#!/usr/bin/env bash
# Deploy AutoBrain to a Linux host over SSH using docker compose.
# Usage: ./scripts/deploy.sh <user@host>
set -euo pipefail

HOST="${1:?Usage: deploy.sh <user@host>}"
REMOTE_DIR="/opt/autobrain"
SSH_ARGS=${SSH_ARGS:-""}

echo "==> Syncing project to $HOST:$REMOTE_DIR"
ssh $SSH_ARGS "$HOST" "mkdir -p $REMOTE_DIR"

# rsync not required; use tar over ssh for portability
tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    --exclude='backend/__pycache__' -czf - . |
  ssh $SSH_ARGS "$HOST" "tar -xzf - -C $REMOTE_DIR"

echo "==> Ensuring .env exists on remote"
ssh $SSH_ARGS "$HOST" "test -f $REMOTE_DIR/.env || cp $REMOTE_DIR/.env.example $REMOTE_DIR/.env"

echo "==> Pulling images and starting production stack"
ssh $SSH_ARGS "$HOST" "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d"

echo "==> Checking health"
sleep 10
curl -fsS "http://$HOST/health" && echo " -> healthy" || echo " -> health check failed (check docker logs)"
