#!/usr/bin/env bash
# Deploy AutoBrain to hosted EP5 (152.69.188.133) with stack 122 digest-pinned.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-152.69.188.133}"
STACK="${STACK:-122}"
STACK_DIGEST="${STACK_DIGEST:-}"
EXCLUDE_STACKS="${EXCLUDE_STACKS:-demo,default}"

echo "==> Deploying stack ${STACK} (digest: ${STACK_DIGEST}) to ${HOST}"
echo "==> Excluding stacks: ${EXCLUDE_STACKS}"

# Ensure stack is digest-pinned (inline) as required
if [ -z "${STACK_DIGEST}" ] || [[ ! "${STACK_DIGEST}" == sha256:* ]]; then
  echo "ERROR: STACK_DIGEST must be set to a sha256 digest for stack ${STACK}" >&2
  exit 1
fi

"$DIR/auto-bump.sh"
"$DIR/check-release.sh"

REMOTE_DIR="~/autobrain"
SSH_ARGS=${SSH_ARGS:-""}
HOST_IP="${HOST#*@}"

ssh "${SSH_ARGS}" "$HOST" "mkdir -p $REMOTE_DIR"

tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    --exclude='backend/__pycache__' --exclude='.env' --exclude='secrets/' -czf - . |
  ssh "${SSH_ARGS}" "$HOST" "tar -xzf - -C $REMOTE_DIR"

ssh "${SSH_ARGS}" "$HOST" "test -f $REMOTE_DIR/.env || cp $REMOTE_DIR/.env.example $REMOTE_DIR/.env"
ssh "${SSH_ARGS}" "$HOST" "cd $REMOTE_DIR && sed -i 's|^API_BASE_URL=.*|API_BASE_URL=http://$HOST_IP/api/v1|; s|^WS_BASE_URL=.*|WS_BASE_URL=ws://$HOST_IP/ws|' .env"

echo "==> Building and starting production stack for stack ${STACK} (digest-pinned)"
ssh "${SSH_ARGS}" "$HOST" "cd $REMOTE_DIR && STACK=${STACK} STACK_DIGEST=${STACK_DIGEST} EXCLUDE_STACKS=${EXCLUDE_STACKS} docker compose -f docker-compose.prod.yml up -d --build"

echo "==> Checking health"
sleep 10
curl -fsS "http://$HOST/health" && echo " -> healthy"
curl -fsS "http://$HOST/api" && echo " -> api healthy" || echo " -> api check failed (check docker logs)"
