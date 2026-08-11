# AutoBrain Documentation

The source of truth for these documents is the team wiki (Outline). The files
below are mirrors kept in-repo for offline reading and PR review.

## Engineering

| Document | Purpose |
|----------|---------|
| [system-overview.md](system-overview.md) | What AutoBrain is and how it fits together |
| [architecture.md](architecture.md) | Component architecture + diagrams |
| [api-spec.md](api-spec.md) | REST + WebSocket API reference |
| [database-schema.md](database-schema.md) | PostgreSQL schema |
| [market-data.md](market-data.md) | CarsGuide/CarSales market data + stable valuations (AUT-287) |
| [product-rules.md](product-rules.md) | Board/product rules that constrain app behaviour (PR-1: club reg disables digital logbook) |
| [ai-models.md](ai-models.md) | AI module descriptions |
| [module-breakdown.md](module-breakdown.md) | AI gateway — per-module breakdown (deterministic-first) |
| [ai-router-integration.md](ai-router-integration.md) | 9Router / AI_ROUTER_URL integration |
| [module-boundaries.md](module-boundaries.md) | Backend + AI gateway module layout & ownership |
| [obd-integration.md](obd-integration.md) | OBD-II port roadmap & next steps |
| [container-architecture.md](container-architecture.md) | Container image layout, healthchecks, upgrade path |
| [infrastructure-diagrams.md](infrastructure-diagrams.md) | Network / container diagrams |
| [deployment-guide.md](deployment-guide.md) | Docker, systemd, k8s deployment + promotion order |
| [server-migration.md](server-migration.md) | Migrating the hosted stack to Oracle Cloud |
| [ci-cd.md](ci-cd.md) | CI/CD pipeline (GitHub Actions, release gates, deploy flow) |
| [versioning.md](versioning.md) | Versioning strategy |
| [changelog.md](changelog.md) | Changelog process (single shared changelog, distribution) |
| [developer-onboarding.md](developer-onboarding.md) | Getting started for devs |
| [security.md](security.md) | Security considerations (MFA, roles, admin provisioning) |
| [backup-strategy.md](backup-strategy.md) | Data backup & restore |
| [monitoring.md](monitoring.md) | Logging and monitoring |
| [mobile-release.md](mobile-release.md) | Mobile `.aab` release runbook + Discord change-notes delivery |
| [payments.md](payments.md) | Stripe plans, pricing, billing flow (sanitised) |
| [test-strategy.md](test-strategy.md) | Test environments, coverage areas, triage flow, sign-off bar |
| [qa-run-logs.md](qa-run-logs.md) | Chronological verified test passes and verification runs |
| [user-testing-results.md](user-testing-results.md) | Verified bug reports, feature verification, test-pass outcomes |

**Rule:** when behaviour changes, update the matching Outline document and the
mirror here in the same change.
