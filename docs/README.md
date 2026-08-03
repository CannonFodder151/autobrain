# AutoBrain Documentation

The source of truth for these documents is the team wiki (Outline). The files
below are mirrors kept in-repo for offline reading and PR review.

| Document | Purpose |
|----------|---------|
| [system-overview.md](system-overview.md) | What AutoBrain is and how it fits together |
| [architecture.md](architecture.md) | Component architecture + diagrams |
| [api-spec.md](api-spec.md) | REST + WebSocket API reference |
| [database-schema.md](database-schema.md) | PostgreSQL schema |
| [ai-models.md](ai-models.md) | AI module descriptions |
| [ai-router-integration.md](ai-router-integration.md) | 9Router / AI_ROUTER_URL integration |
| [deployment-guide.md](deployment-guide.md) | Docker, systemd, k8s deployment |
| [developer-onboarding.md](developer-onboarding.md) | Getting started for devs |
| [versioning.md](versioning.md) | Versioning strategy |
| [security.md](security.md) | Security considerations (MFA, roles, admin provisioning) |
| [backup-strategy.md](backup-strategy.md) | Data backup & restore |
| [monitoring.md](monitoring.md) | Logging and monitoring |
| [infrastructure-diagrams.md](infrastructure-diagrams.md) | Network / container diagrams |

**Rule:** when behaviour changes, update the matching Outline document and the
mirror here in the same change.
