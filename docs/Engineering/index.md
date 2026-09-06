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

### OBD

| Document | Purpose |
|----------|---------|
| [obd-integration.md](./obd-integration.md) | OBD-II port roadmap & next steps |
| [obd2-dongle/README.md](./obd2-dongle/README.md) | OBD-II dongle firmware builds |
| [obd2-dongle/nodemcu32s-build-guide.md](./obd2-dongle/nodemcu32s-build-guide.md) | NodeMCU-32S build guide |

### ADRs

- [adr/0001-ownership-advisor.md](./adr/0001-ownership-advisor.md)
