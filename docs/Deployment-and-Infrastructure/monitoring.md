# Monitoring & Logging

## Current monitoring setup

All tiers are managed through **Portainer** (`https://portainer.nathanmartina.com`,
`X-API-Key: portainer_api_key`). Portainer shows container state + healthcheck
badges per service, per environment:

- **Hosted** — endpoint **5** (`autobrain-hosted` stack #122, Oracle Cloud VM
  152.69.188.133). 7 long-running containers: `postgres`, `redis`, `minio`,
  `backend`, `dongle-server`, `frontend`, `hub`, `9router`, `autobrain-backup`.
- **Dev** — endpoint **6** (this dev box, `autobrain-dev` stack #109).
- **Demo / Default** — endpoint **2** (Portainer-Host; redeploys paused per
  AUT-2409, still monitored).
- `rego-lookup` (EP5 stack #85), `autobrain-backup` (EP2 stack #84),
  `gh-runner-autobrain-arm64` (EP5 stack #123), `fw-keeper`, `npm` and the
  Portainer agent also appear in the same view.

There is **no standalone `worker` container** in the hosted stack (AUT-3153) —
Celery worker+beat, the AI gateway (`:8001`) and the market-data scraper all run
as background processes inside `backend` (AUT-3810). Celery problems surface in
the **backend** container log, not a separate worker log.

## Logging

- Backend + AI use **structlog** → JSON lines on stdout, captured by Docker.
- Celery worker + beat log via Python logging to stdout, in the backend
  container (AUT-3153).
- All containers have Docker healthchecks (see Dockerfiles / compose):
  - backend → `/health` (probes the FastAPI app on `:8000`)
  - postgres → `pg_isready`
  - redis → `redis-cli -a $(cat /run/secrets/redis_password) ping`
  - minio → `mc ready local`
  - dongle-server → python `urllib` GET `/health`
  - hub → python `urllib` GET `/health`
  - `9router`, `fw-keeper`, `npm`, `gh-runner` → no healthcheck (system-level,
    watch container state + reachability probes instead)

## Metrics / dashboards

Deploy Prometheus + Grafana, or use the Docker healthchecks with a simple
uptime monitor:

| Signal | Source |
|--------|--------|
| Uptime / restarts | `docker ps`, Portainer container list |
| Health | Portainer healthcheck badges; `curl /health` per tier |
| API errors | backend JSON logs (grep `"level":"error"`) |
| Router status | `GET http://backend:8001/health` → `router_enabled` (AI gateway merged into backend, AUT-3810) |
| OCR failures | `ocr_status=failed` in receipts |
| Queue depth | Celery `inspect active`, Redis `llen` on broker queues |
| Disk | `df -h` (backups + MinIO grow fastest) |
| AI fallback rate | Log grep for `router_unreachable_using_fallback` (indicates router down; system works via fallbacks) |
| Backup health | `autobrain-backup` web GUI (port 8080, `127.0.0.1` on Hosted) health/stats; email alerts on failure/corruption |
| Firewall rules | `fw-keeper` (host-level iptables) restricts `:9001` (Portainer agent) to `122.199.30.128/32` and `:20128` (9Router) to dev egress + internal subnet; verify via external probe (check-host.net) that non-allowlisted IPs time out |

## Alerting

- Healthcheck failures → restart (`restart: unless-stopped`) + investigate.
- Watch `processor` for AI fallback usage: `router_unreachable_using_fallback`
  indicates the 9Router is down (system still works via fallbacks).
- Service status → `#status` channel; incidents → `#incidents` channel
  (Deployment team owns triage).
- `autobrain-backup` sends email alerts on backup failure/corruption.

## Tracing (future)

When needed, add OpenTelemetry to the FastAPI apps and export to
OTLP/collector. A Grafana instance exists on Portainer-Host; wire dashboards
when metrics exporters are deployed.
