# Monitoring & Logging

## Logging

- Backend + AI use **structlog** → JSON lines on stdout, captured by Docker.
- Celery worker logs via Python logging to stdout.
- All containers have Docker healthchecks (see Dockerfiles / compose):
  - backend → `/health`
  - ai → `/health`
  - postgres → `pg_isready`
  - redis → `redis-cli ping`
  - minio → `mc ready local`

## Metrics / dashboards (recommended)

Deploy Prometheus + Grafana, or use the Docker healthchecks with a simple
uptime monitor:

| Signal | Source |
|--------|--------|
| Uptime / restarts | `docker ps`, systemd status |
| API errors | backend JSON logs (grep `"level":"error"`) |
| Router status | `GET http://ai:8001/health` → `router_enabled` |
| OCR failures | `ocr_status=failed` in receipts |
| Queue depth | Celery `inspect active`, Redis `llen` on broker queues |
| Disk | `df -h` (backups + MinIO grow fastest) |

## Alerting

- Healthcheck failures → restart (`restart: unless-stopped`) + notify via
  your monitor.
- Watch `processor` for AI fallback usage: `router_unreachable_using_fallback`
  indicates the 9Router is down (system still works via fallbacks).

## Tracing (future)

When needed, add OpenTelemetry to the FastAPI apps and export to
OTLP/collector.
