# Runbooks

Operational runbooks for common and critical operations.

## Document List

| Document | Purpose |
|----------|---------|
| [deploy.md](./deploy.md) | Deploy AutoBrain to Demo, Default, and Hosted tiers |
| [backup-restore.md](./backup-restore.md) | Admin backup, off-site backup, and disaster recovery |
| [database-migration.md](./database-migration.md) | Alembic migration procedures and troubleshooting |
| [secret-rotation.md](./secret-rotation.md) | Rotate secrets (JWT, API keys, passwords, database) |
| [health-check.md](./health-check.md) | Service health verification and troubleshooting |
| [incident-response.md](./incident-response.md) | Incident classification, escalation, and resolution |

## Adding a Runbook

When creating a new runbook:
1. Use the naming pattern: `<operation>.md` (kebab-case)
2. Include: Overview, Prerequisites, Step-by-step procedure, Verification, Rollback, Related docs
3. Add an entry to this index table
4. Link from the relevant section index (Deployment & Infrastructure, Security, etc.)
