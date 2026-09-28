# Container Consolidation Migration (AUT-3153)

## Summary

**AUT-3153 (Phase 1a): Merge the standalone `worker` Celery container into `backend`.**

Before: `backend` (API `:8000`) + `worker` (Celery worker + beat `-B`) = 2 containers.
After: single `backend` container runs uvicorn **and** Celery worker+beat in the background.

This reduced the container count, simplified deployments, and eliminated a
separate image build/push pipeline (`autobrain-worker`).

---

## What changed

### Compose (both `docker-compose.prod.yml` and `docker-compose.hosted.yml`)

- **Removed** the `worker` service block entirely.
- **Updated** `backend.command` to start Celery in the background, then exec uvicorn:

  ```yaml
  command: >
    sh -c "export AI_ROUTER_API_KEY=$(cat /run/secrets/ai_router_api_key) &&
           python -m app.db.bootstrap &&
           (celery -A app.workers.celery_app:celery_app worker -B -l info --concurrency=2 &) &&
           exec uvicorn app.main:app --host 0.0.0.0 --port 8000"
  ```

- **Moved** `FUEL_*_FILE` secrets from the old `worker` environment block into `backend`
  (the fuel-poll tasks now run in the backend container).

### Dockerfiles

- `docker/backend/Dockerfile` — unchanged (already had Celery deps + entrypoint logic).
- `docker/worker/Dockerfile` — **retained on disk for reference only**; no longer
  referenced by any compose file. The build is retired from CI.

### CI

- `dockerhub-publish.yml` — still builds `autobrain-worker` as part of its
  matrix (legacy; the matrix still includes `worker` to keep the per-arch
  publishing idempotent). The `:hosted` manifest for `worker` is assembled but
  **never deployed**.
- `build-hosted.yml` — still builds `worker` (matrix includes it) for the same
  reason; the `compose-pin` job still emits a `worker_digest` but it is **not
  consumed** by `docker-compose.hosted.yml` (no `worker` service). Future
  cleanup: drop `worker` from the matrix and the compose-pin step (AUT-3172).

### Portainer stacks

- **Hosted (EP5, `autobrain-hosted`)**: no `worker` service. Stack has 12
  containers: postgres, redis, minio, backend, ai, dongle-server, frontend, hub,
  gh-runner, 9router, autobrain-backup, backup-agent.
- **Demo/Default (EP2, PAUSED per AUT-2409)**: same — no `worker` service.

### Runtime behaviour

- `backend` container runs **two** long-lived processes:
  1. Celery worker + beat (background, `&`)
  2. uvicorn (foreground, `exec` — PID 1)
- If uvicorn crashes, the container exits and Portainer restarts it
  (`restart: unless-stopped`). The background Celery also dies and restarts
  with the container — this is intentional; no orphan workers.
- Logs: both uvicorn and Celery emit to stdout (Docker captures both).
- Healthcheck: unchanged — probes `GET /health` on uvicorn.

---

## Why

- **Container reduction**: 2 → 1 app container; fewer moving parts.
- **Image pipeline simplification**: one less multi-arch image to build, scan,
  sign, push, pin, prune.
- **Secret handling**: one fewer secret-file bind mount set.
- **Network**: no inter-container Celery↔Redis hop (already shared the same
  Redis, but now the worker is local to the same container network namespace).
- **Operations**: `docker logs backend` now shows both API requests and
  background job processing; no need to tail two containers.

---

## Rollback

If a regression appears, revert `docker-compose.hosted.yml` / `docker-compose.prod.yml`
to the pre-merge versions (tag `pre-aut3153` or the commit before the merge)
and redeploy. The DB schema is unchanged; Celery beat schedule is identical
(same `celery_app` module). No data migration needed.

---

## Follow-up (AUT-3172)

Retire `autobrain-worker` from CI entirely:

1. Drop `worker` from the matrix in `dockerhub-publish.yml` and `build-hosted.yml`.
2. Drop `worker_digest` from `compose-pin` job outputs and the `update-compose-pins.py` script.
3. Optionally delete `docker/worker/Dockerfile` (or move to `archives/`).

---

**Related:** [`deployment-guide.md`](./deployment-guide.md) | [`ci-cd.md`](./ci-cd.md) | [`docker-compose.hosted.yml`](../../docker-compose.hosted.yml) | [`docker-compose.prod.yml`](../../docker-compose.prod.yml)

**Graft usage:** This repo is indexed with Graft (trailhq/Graft). Run `graft map` to orient, `graft ask "<task>"` to find code, `graft grep "<regex>"` for exhaustive search, `graft callers <symbol>` for call graphs, `graft blast --base origin/main` for diff blast radius. See `AGENTS.md` for agent integration.