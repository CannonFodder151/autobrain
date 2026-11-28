# Security

Security posture, secrets policy, incident runbooks.

## Document List

| Document | Purpose |
|----------|---------|
| [security.md](./security.md) | Security considerations (MFA, roles, admin provisioning) |

## Runbooks

| Runbook | Purpose |
|---------|---------|
| [../runbooks/secret-rotation.md](../runbooks/secret-rotation.md) | Rotate secrets (JWT, API keys, passwords, database) |
| [../runbooks/incident-response.md](../runbooks/incident-response.md) | Incident classification, escalation, and resolution |

**Note:** Per-instance secrets, API keys, and internal deployment endpoints are stored in Outline (internal-only). Public repo mirrors are always sanitised.
