# Monitoring & Logging

Covers the **Hosted** production stack (Oracle Cloud VM `152.69.188.133`, Portainer
EP5, stack `autobrain-hosted`). Demo/Default are **PAUSED** per AUT-2409 and share
the same compose shape — see `deployment-guide.md` for the tier table.

## Current monitoring setup

The Hosted stack is managed through **Portainer** (endpoint 5 = AutoBrain-Hosted,
`https://portainer.nathanmartina.com`). Portainer shows container state + healthcheck
badges per service:

- **Hosted** (Oracle Cloud VM, EP5).
- Rego Lookup (stack `rego-lookup`, EP5, loopback only).
- 9Router runs inside the hosted stack; Portainer shows its container health.

## Logging

- Backend + AI use **structlog** → JSON lines on stdout, captured by Docker.
- Celery worker + beat (merged into the `backend` container) log via Python logging to stdout.
- All containers have Docker healthchecks (see Dockerfiles / compose):
  - backend → `/health`
  - ai → `/health`
  - postgres → `pg_isready`
  - redis → `redis-cli -a <password> ping`
  - minio → `mc ready local`
  - frontend → probes `http://backend:8000/health` (AUT-2389)
  - hub → probes `http://localhost:8000/health`
  - autobrain-backup → probes `/health` on loopback `:8080`

Logs are viewable in Portainer (per-container) or via `docker logs <container>` on the VM.

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
| Backup health | `autobrain-backup` web GUI (`http://127.0.0.1:8080/health`) health/stats; email alerts on failure/corruption |
| Firewall health | `fw-keeper` container running (enforces `:9001`, `:20128` allow-lists) |

## Alerting

- Healthcheck failures → restart (`restart: unless-stopped`) + investigate.
- Watch `processor` for AI fallback usage: `router_unreachable_using_fallback`
  indicates the 9Router is down (system still works via fallbacks).
- Service status → `#status` channel; incidents → `#incidents` channel
  (Deployment team owns triage).
- `autobrain-backup` sends email alerts on backup failure/corruption.

## Tracing (future)

When needed, add OpenTelemetry to the FastAPI apps and export to
OTLP/collector. A Grafana instance exists on Portainer-Host (EP2); wire dashboards
when metrics exporters are deployed. For Hosted, consider a hosted Grafana or
CloudWatch metrics forwarder.

---

**Related docs:** [`deployment-guide.md`](./deployment-guide.md) | [`backup-strategy.md`](./backup-strategy.md) | [`infrastructure-diagrams.md`](./infrastructure-diagrams.md) | [`security.md`](../Security/security.md)

**Graft usage:** This repo is indexed with Graft (trailhq/Graft). Run `graft map` to orient, `graft ask "<task>"` to find code, `graft grep "<regex>"` for exhaustive search, `graft callers <symbol>` for call graphs, `graft blast --base origin/main` for diff blast radius. See `AGENTS.md` for agent integration.