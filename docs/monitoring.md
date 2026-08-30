# Monitoring & Logging

## Current monitoring setup

All tiers are managed through **Portainer** (managed access point — see the ops
docs for the URL and endpoints). Portainer shows container state + healthcheck
badges per service, per environment:

- **Demo / Default** (dev box).
- **Hosted** (Oracle Cloud VM).
- Rego Lookup, backup service and the 9Router instance also run as Portainer
  stacks and appear in the same view.

## Logging

- Backend + AI use **structlog** → JSON lines on stdout, captured by Docker.
- Celery worker + beat log via Python logging to stdout.
- All containers have Docker healthchecks (see Dockerfiles / compose):
  - backend → `/health`
  - ai → `/health`
  - postgres → `pg_isready`
  - redis → `redis-cli ping`
  - minio → `mc ready local`

## Metrics / dashboards

Deploy Prometheus + Grafana, or use the Docker healthchecks with a simple
uptime monitor:

| Signal | Source |
|--------|--------|
| Uptime / restarts | `docker ps`, Portainer container list |
| Health | Portainer healthcheck badges; `curl /health` per tier |
| API errors | backend JSON logs (grep `"level":"error"`) |
| Router status | `GET http://ai:8001/health` → `router_enabled` |
| OCR failures | `ocr_status=failed` in receipts |
| Queue depth | Celery `inspect active`, Redis `llen` on broker queues |
| Disk | `df -h` (backups + MinIO grow fastest) |
| AI fallback rate | Log grep for `router_unreachable_using_fallback` (indicates router down; system works via fallbacks) |
| Backup health | `autobrain-backup` web GUI (port 8080) health/stats; email alerts on failure/corruption |

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
