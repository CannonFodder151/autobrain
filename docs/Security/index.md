# Security

Security posture, secrets policy, incident runbooks.

This public mirror tracks the internal Outline "Security" pages. Per-instance
secrets, API keys, and internal endpoints live only in Outline — see the
[Documentation Policy](../Company/documentation-policy.md).

## Document List

| Document | Purpose |
|----------|---------|
| [security.md](./security.md) | Security posture: auth, MFA, roles, secrets, network, containers, pgvector, federated hub |
| [incident-response.md](./incident-response.md) | Incident runbook: severity, triage, comms, postmortem |
| [SECURITY.md](../../SECURITY.md) | Vulnerability reporting policy |

## Related docs

- [Container Architecture](../Engineering/container-architecture.md) — non-root containers, `read_only`/`cap_drop`, service images + ports
- [System Overview](../Engineering/system-overview.md) — runtime hardening (uid 1000, read-only, tmpfs)
- [Vector Store](../Engineering/ai/vector.md) — pgvector schema and embeddings
- [PostgreSQL 17 Upgrade](../Engineering/postgresql-17-upgrade.md) — DB version + digest pinning
- [Monitoring & Logging](../Deployment-and-Infrastructure/monitoring.md) — health checks + incident detection
- [9Router Integration](../Engineering/ai-router-integration.md) — AI router auth/routing
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md) — deploy/run secrets

**Note:** Per-instance secrets, API keys, internal deployment endpoints (e.g.
`<DEV_EGRESS_IP>`, the internal docker subnet), and board-sensitive notes are
stored in Outline only. Public repo mirrors are always sanitised.
