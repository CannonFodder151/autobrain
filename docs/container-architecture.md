# Container Architecture

## Compose (dev)

`docker-compose.yml`: postgres, redis, minio, minio-init, backend (reload),
worker, beat, ai (reload), frontend. Source volumes for hot reload.

## Compose (prod)

`docker-compose.prod.yml`: same core, ENVIRONMENT=production, no source
mounts, nginx reverse proxy published on :80, backend/ai only exposed
internally.

## Image layout

Each service runs as non-root (`autobrain` uid 1000), has a healthcheck, and
reads configuration exclusively from environment variables.

## Healthchecks

- backend: `curl -fsS /health`
- ai: `curl -fsS /health`
- worker: `celery inspect ping`
- postgres/redis/minio: native probes (see compose)

## Upgrade path

- Deploys are run manually from the repo: `docker compose -f docker-compose.prod.yml build && up -d`, or via `scripts/deploy.sh`. `docker compose up -d` is zero-downtime for backend/ai since nginx routes to running containers.
- DB migrations run inside the backend container on boot (`app.db.bootstrap`).
