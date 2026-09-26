# AutoBrain Infrastructure Costs

Infrastructure spend tracking for AutoBrain environments, separate from agent LLM costs (see [Budget Tracking](budget-tracking.md)).

## Environment Overview

| Environment | Host / IP | Portainer Endpoint | Purpose |
|-------------|-----------|-------------------|---------|
| **Dev** | 10.0.3.39 | 6 = PaperClip-AutoBrain-Dev-Box | Dev box; Paperclip control plane + dev stack |
| **Demo** | 10.0.3.17 | 2 = Portainer-Host | Demo stack; separate compose file |
| **Default** | 10.0.3.17 | 2 = Portainer-Host | Default stack; separate compose file |
| **Hosted (Production)** | 152.69.188.133 | 5 = AutoBrain-Hosted | ARM cloud VM; public server; federation hub; highly available |

## Hosted Production (Oracle Cloud) — Current Spend

Production stack runs on Oracle Cloud VM `152.69.188.133` (Portainer endpoint 5). Services on this VM:

- AutoBrain API (FastAPI) + Celery workers
- PostgreSQL database
- MinIO object storage
- AI gateway (5 modules)
- 9Router instance (hosted-local AI routing)
- Rego Lookup API
- Nginx reverse proxy

### Estimated Monthly Costs (Oracle Cloud)

| Resource | Budget | Est. Actual | Notes |
|----------|--------|-------------|-------|
| VM Compute (ARM shape) | $50 AUD | $25–50 AUD | API, workers, 9Router |
| Block Storage | $15 AUD | $5–10 AUD | PostgreSQL + MinIO volumes |
| Network Egress | $20 AUD | $5–15 AUD | Variable by traffic |
| **Total** | **$85 AUD** | **~$35–75 AUD** | Within budget |

*Actual invoice amount is the source of truth — check Oracle Cloud Console billing before month-end close.*

## On-Prem Development (Hidden Costs)

The dev box at `10.0.3.39` runs on local hardware — no cloud bill, but real cost:

| Resource | Est. Monthly | Notes |
|----------|--------------|-------|
| Electricity | $10–20 AUD | 24/7 availability |
| Hardware Depreciation | $15–30 AUD | Server amortised over 3 years |
| Network (residential) | $5–10 AUD | Static IP + bandwidth |
| Engineer time / maintenance | Unquantified | Reinstalls, upgrades, hardware failure |
| **Total** | **~$30–60 AUD + intangibles** | Not on any invoice |

**Note:** the same box also runs Demo/Default stacks (10.0.3.17, Portainer endpoint 2) — those marginal costs are lower (no incremental hardware).

## Stack Components and Cost Drivers

| Component | Dev | Demo/Default | Hosted | Primary Cost Driver |
|-----------|-----|--------------|--------|--------------------|
| FastAPI backend | ✓ | ✓ | ✓ | CPU/RAM |
| Celery workers | ✓ | ✓ | ✓ | CPU (background AI jobs) |
| PostgreSQL | ✓ | ✓ | ✓ | Storage + RAM |
| MinIO | ✓ | ✓ | ✓ | Storage growth |
| AI gateway (5 modules) | ✓ | ✓ | ✓ | Network + 9Router tokens |
| 9Router (hosted-local) | remote | remote | ✓ | GPU/CPU inference on VM |
| Rego Lookup API | ✓ | ✓ | ✓ | CPU (deterministic) |
| Flutter web (static) | ✓ | ✓ | ✓ | Nginx, negligible |
| Nginx | ✓ | ✓ | ✓ | Minimal |

**ponytail:** per-service cost attribution is not currently measurable. Estimate from VM totals until Oracle Cloud per-VM/per-OCPU cost attribution is available.

## Cost Tracking Gaps

- [ ] Oracle Cloud actual billing API integration into the dashboard
- [ ] Per-service CPU/RAM/disk attribution (Portainer stats are per-container, not per-cost)
- [ ] Network egress breakdown by service
- [ ] MinIO storage growth projection and archive policy
- [ ] PostgreSQL backup retention cost (backup volume size × growth)
- [ ] 9Router token spend attribution (which AI features consume it)

## Cost Optimization Opportunities

1. **Container consolidation** (Phase 1 goal) — fewer services = less RAM/disk, fewer moving parts. A single process can host API + gateway + rego-lookup.
2. **Deterministic-first AI paths** (Phase 1 goal) — rego lookup, fuel pricing, market data are deterministic; keeping them off the AI path directly cuts 9Router spend.
3. **Dev box right-sizing** — evaluate whether dev needs the full stack or a reduced profile.
4. **Storage tiering** — cold MinIO objects (older vehicle photos, cached market data) to a cheaper tier or lifecycle-expire.
5. **Off-hours scaling** — scale down dev workers when idle; Celery is the main dev CPU consumer.
6. **ARM shape preference** — hosted VM is already ARM; keep new services on ARM-compatible images to avoid emulation cost.

## Reporting

- **Monthly Infra Report** — Outline page `Finance/Infrastructure Costs/YYYY-MM`
- **Discord Digest** — included in the weekly `#ops` post
- **Oracle Cloud Console** — primary source for hosted costs
- **Portainer** — per-container stats (`/api/endpoints/{id}/docker/stats`)

---

*Last updated: 2026-09-26 | Owner: CFO | Sources: Oracle Cloud Console, Portainer, migration cost case | Next review: 2026-10-26*