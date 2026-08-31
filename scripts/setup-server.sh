#!/usr/bin/env bash
# One-time server bootstrap: installs docker + compose if missing, creates dirs.
# Usage: sudo ./scripts/setup-server.sh [user]
set -euo pipefail

USER_NAME="${1:-$(whoami)}"
REMOTE_DIR="/opt/autobrain"
# AUT-1853: Hosted stack uses /data/autobrain/secrets (snap Docker masks /opt)
SECRETS_DIR="/data/autobrain/secrets"

echo "==> Installing docker if missing"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

echo "==> Installing docker compose plugin if missing"
docker compose version >/dev/null 2>&1 || {
  apt-get update
  apt-get install -y docker-compose-plugin
}

echo "==> Creating app directory"
mkdir -p "$REMOTE_DIR"
mkdir -p "$SECRETS_DIR"

echo "==> Adding user $USER_NAME to docker group"
usermod -aG docker "$USER_NAME" || true

echo "==> Done. Deploy with: ./scripts/deploy.sh $USER_NAME@<host>"
