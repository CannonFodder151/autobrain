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
| [container-consolidation-migration.md](./container-consolidation-migration.md) | AUT-3153 worker→backend merge + image retirements |

## Per-instance secrets & API keys

**Outline only — internal secrets, NOT in this public repo.** The canonical
per-instance secrets list for Hosted (Oracle Cloud VM `152.69.188.133`, EP5,
stack `autobrain-hosted`) lives in **Outline → AutoBrain collection →
Per-Instance Secrets & API Keys**. Do not mirror secret values here.

The secret-file pattern (AUT-1533) is described in
[`security.md`](../Security/security.md) → "Secret-file pattern & broker auth".

---

**Graft usage:** This repo is indexed with Graft (trailhq/Graft). Run `graft map` to orient, `graft ask "<task>"` to find code, `graft grep "<regex>"` for exhaustive search, `graft callers <symbol>` for call graphs, `graft blast --base origin/main` for diff blast radius. See `AGENTS.md` for agent integration.