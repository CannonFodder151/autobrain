# Engineering

Architecture, API, database, AI modules, OBD, mobile, developer onboarding, versioning.

## Document List

### Core

| Document | Purpose |
|----------|---------|
| [architecture.md](./architecture.md) | Component architecture + diagrams |
| [api-spec.md](./api-spec.md) | REST + WebSocket API reference |
| [integrating-autobrain.md](./integrating-autobrain.md) | Human-readable integration guide (users + auth) |
| [database-schema.md](./database-schema.md) | PostgreSQL schema |
| [container-architecture.md](./container-architecture.md) | Container image layout, healthchecks, upgrade path |
| [infrastructure-diagrams.md](./infrastructure-diagrams.md) | Network / container diagrams |
| [developer-onboarding.md](./developer-onboarding.md) | Getting started for devs |
| [versioning.md](./versioning.md) | Versioning strategy |
| [task-pipeline.md](./task-pipeline.md) | Sub-task & follow-up creation pattern, curl examples |
| [system-overview.md](./system-overview.md) | End-to-end system overview + component table |
| [postgresql-17-upgrade.md](./postgresql-17-upgrade.md) | PG17 + pgvector upgrade notes + digest pin rationale |
| [safpis-sa-fuel-api-research.md](./safpis-sa-fuel-api-research.md) | SA FPIS fuel API research + integration plan |

### AI & Modules

| Document | Purpose |
|----------|---------|
| [module-breakdown.md](./module-breakdown.md) | AI gateway — per-module breakdown (deterministic-first) |
| [module-boundaries.md](./module-boundaries.md) | Backend + AI gateway module layout & ownership |
| [ai-models.md](./ai-models.md) | AI module descriptions |
| [ai-router-integration.md](./ai-router-integration.md) | 9Router / AI_ROUTER_URL integration |
| [ai/vector.md](./ai/vector.md) | Vector store schema, embedding pipeline, hybrid search |

### Mobile & Releases

| Document | Purpose |
|----------|---------|
| [mobile-release.md](./mobile-release.md) | Mobile `.aab` release runbook + Discord change-notes delivery |

### Integrations

| Document | Purpose |
|----------|---------|
| [../home-assistant-integration.md](../home-assistant-integration.md) | Home Assistant REST integration setup + API reference |

### OBD

| Document | Purpose |
|----------|---------|
| [obd-integration.md](./obd-integration.md) | OBD-II port roadmap & next steps |
| [obd2-dongle/README.md](./obd2-dongle/README.md) | OBD-II dongle firmware builds |
| [obd2-dongle/nodemcu32s-build-guide.md](./obd2-dongle/nodemcu32s-build-guide.md) | NodeMCU-32S build guide |

### ADRs

- [adr/0001-ownership-advisor.md](./adr/0001-ownership-advisor.md)

### VASS — Vehicle Approval & Modification Compliance

Deterministic ADR/VSI/VSB6 modification compliance. **Not merged yet** — see
[vass/index.md](./vass/index.md) for per-area status.

| Document | Purpose |
|----------|---------|
| [vass/index.md](./vass/index.md) | VASS overview + status table |
| [vass/data-models.md](./vass/data-models.md) | `VASRule` / `VASCheck`, enums, ADR class taxonomy |
| [vass/api.md](./vass/api.md) | `/vass/check`, `/vass/rules`, rule CRUD |
| [vass/rule-engine.md](./vass/rule-engine.md) | Deterministic evaluation + status fold |
| [vass/standards-catalog.md](./vass/standards-catalog.md) | ADR / VSI / VSB6 citations + seeding contract |
| [vass/vector-corpus.md](./vass/vector-corpus.md) | Planned regulatory corpus vector store (blocked) |
| [vass/pre-check-wizard.md](./vass/pre-check-wizard.md) | Pre-check wizard flow (Flutter, not started) |
| [vass/compliance-packs.md](./vass/compliance-packs.md) | PDF/HTML compliance packs (not started) |
