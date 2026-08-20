# Container Architecture

## Compose (dev)

`docker-compose.yml`: postgres, redis, minio, backend (reload, runs API +
Celery worker+beat), ai (reload), frontend. Source volumes for hot reload.

## Compose (prod)

`docker-compose.prod.yml`: same core, ENVIRONMENT=production, no source
mounts, nginx reverse proxy published on :80, backend/ai only exposed
internally. Backend runs the API + Celery worker+beat in one container.

## Compose (hosted)

`docker-compose.hosted.yml`: prebuilt tagged images (`cannonfodder151/autobrain-*:hosted`), frontend on :8086, Stripe billing env vars, self-signup + MFA enforced. Deployed via Portainer on the Oracle Cloud VM. Dedicated worker container runs Celery worker + beat (`-B`), single container (AUT-1242/C1).

## Image layout

Each service runs as non-root (`autobrain` uid 1000), has a healthcheck, and
reads configuration exclusively from environment variables. The backend image
is unified: API + AI gateway modules + Celery worker/beat entrypoint; `ai` runs
as a separate process container for OCR/AI isolation.

## Healthchecks

- backend: `curl -fsS /health`
- ai: `curl -fsS /health`
- postgres/redis/minio: native probes (see compose)

## Upgrade path

- Deploys are run manually from the repo: `docker compose -f docker-compose.prod.yml build && up -d`, or via `scripts/deploy.sh`. `docker compose up -d` is zero-downtime for backend/ai since nginx routes to running containers.
- DB migrations run inside the backend container on boot (`app.db.bootstrap`).
