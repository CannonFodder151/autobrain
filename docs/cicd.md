# CI/CD Pipeline

## CI (`.github/workflows/ci.yml`)

Runs on every push to `main` and every PR:

1. **Backend:** setup Python 3.12 + postgres/redis services → `ruff check` → `pytest`.
2. **AI:** setup Python → `ruff check` → `pytest` (router disabled path).
3. **Frontend:** Flutter (stable) → `pub get` → `flutter analyze` → `flutter test`.
4. **Docker build:** builds backend, AI and worker images to catch Dockerfile
   regressions.

## CD (`.github/workflows/deploy.yml`)

On merge to `main` (paths: backend/ai/docker/compose) or manual dispatch:

1. SSH to `DEPLOY_HOST` (secrets: `DEPLOY_USER`, `DEPLOY_SSH_KEY`).
2. `git fetch` + `reset --hard origin/main` in `/opt/autobrain`.
3. `docker compose -f docker-compose.prod.yml build && up -d`.
4. Health-check `http://localhost/health`.

## Required repo secrets

| Secret | Purpose |
|--------|---------|
| `DEPLOY_HOST` | Server host/IP |
| `DEPLOY_USER` | SSH user |
| `DEPLOY_SSH_KEY` | Private key |
| `DEPLOY_PORT` | Optional, default 22 |
