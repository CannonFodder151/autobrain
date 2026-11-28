# Deployment & Infrastructure

Compose stacks, hosted/prod topologies, backup, monitoring, deployment guides, CI/CD.

## Document List

| Document | Purpose |
|----------|---------|
| [deployment-guide.md](./deployment-guide.md) | Docker, systemd, k8s deployment + promotion order |
| [infrastructure-diagrams.md](./infrastructure-diagrams.md) | Network / container diagrams |
| [ci-cd.md](./ci-cd.md) | CI/CD pipeline (GitHub Actions, release gates, deploy flow) |
| [server-migration.md](./server-migration.md) | Migrating the hosted stack to Oracle Cloud |
| [backup-strategy.md](./backup-strategy.md) | Data backup & restore |
| [monitoring.md](./monitoring.md) | Logging and monitoring |
| [autobrain-deploy-trigger.md](./autobrain-deploy-trigger.md) | n8n deploy trigger |

## Runbooks

| Runbook | Purpose |
|---------|---------|
| [../runbooks/deploy.md](../runbooks/deploy.md) | Deploy to Demo, Default, Hosted tiers |
| [../runbooks/backup-restore.md](../runbooks/backup-restore.md) | Backup, restore, disaster recovery |
| [../runbooks/database-migration.md](../runbooks/database-migration.md) | Alembic migration procedures |
| [../runbooks/secret-rotation.md](../runbooks/secret-rotation.md) | Rotate secrets across environments |
| [../runbooks/health-check.md](../runbooks/health-check.md) | Service health verification |
| [../runbooks/incident-response.md](../runbooks/incident-response.md) | Incident classification & response |

**Note:** Per-instance secrets and API keys live in Outline (internal-only). Do not mirror to this public repo.
