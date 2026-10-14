# Incident Response Runbook

How AutoBrain responds to a service incident. Owned by the Deployment team
(triage); the CTO owns postmortem and remediation.

## Severity levels

| Level | Definition | Target response | Paged |
|-------|-----------|-----------------|-------|
| **SEV-1** | Public outage / data loss / security breach | < 5 min | Yes |
| **SEV-2** | Degraded service, or feature down for a subset | < 15 min | Yes |
| **SEV-3** | Anomaly with workaround, no user impact | < 1 h | No |

## Detection

- Portainer healthcheck badges per service, per environment (Demo / Default / Hosted).
- Backend JSON logs (`"level":"error"`), Celery queue depth, router health
  (`GET http://ai:8001/health` → `router_enabled`).
- AI fallback rate: `router_unreachable_using_fallback` in logs means the
  9Router is down (system still works via fallbacks).
- Backup health: `backup` web GUI (port 8080) health/stats; email alerts on
  failure/corruption.
- Uptime/restart: `docker ps`, Portainer container list.

## Triage

1. **Verify the report.** Reproduce from a clean client; check the relevant
   environment (Demo / Default / Hosted) and the healthcheck for the affected
   service.
2. **Classify severity** (above) and **stop the bleeding** first — roll back the
   last deploy, restart the failing service, or fail over to the healthy tier.
3. **Communicate.** Post to `#incidents` (active, `0xED4245`) with severity,
   affected scope, and ETA. Update as the picture changes.
4. **Escalate.** Deployment team owns triage. If it is a security incident,
   follow [SECURITY.md](../../SECURITY.md) (email `security@nathanmartina.com`,
   48-hour response SLA) and do NOT open a public issue.
5. **Restore.** Once stable, confirm healthchecks green and the affected tier
   is serving normally.

## Comms

- **Active incident:** `#incidents` — one-line summary + severity + scope + ETA.
- **Resolved:** `#incidents` (resolved, `0xE67E22`) + `#updates` (what shipped
  / fixed). Do not spam; one post per incident change is enough.
- **Customer-facing:** `#support` / `#changelog` only when customers are
  affected.
- Never post bare text — always an embed via the n8n Discord Reporter.

## Postmortem

- Write the postmortem within 48h of resolution. Template: timeline, impact,
  root cause, action items (owner + date), and prevention check.
- File the postmortem in Outline (AutoBrain collection) and link it from the
  incident thread.
- Action items feed the engineering backlog as Paperclip issues.

## Related docs

- [Security Considerations](./security.md) — stack hardening, secrets, network
- [Monitoring & Logging](../Deployment-and-Infrastructure/monitoring.md) —
  signals and alerting
- [Container Architecture](../Engineering/container-architecture.md) —
  non-root containers, images and ports
- [SECURITY.md](../../SECURITY.md) — vulnerability reporting policy