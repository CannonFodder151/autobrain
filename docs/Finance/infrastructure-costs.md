# AutoBrain Infrastructure Costs

Infrastructure spend tracking for AutoBrain environments, separate from agent LLM costs (see [Budget Tracking](budget-tracking.md)).

## Environment Overview

| Environment | Host / IP | Portainer Endpoint | Purpose |
|-------------|-----------|-------------------|---------|
| **Dev** | <DEV_BOX_IP> | 6 = PaperClip-AutoBrain-Dev-Box | Dev box; Paperclip control plane + dev stack |
| **Demo** | <PORTENER_HOST_IP> | 2 = Portainer-Host | Demo stack; separate compose file |
| **Default** | <PORTENER_HOST_IP> | 2 = Portainer-Host | Default stack; separate compose file |
| **Hosted (Production)** | <HOSTED_VM_IP> | 5 = AutoBrain-Hosted | ARM cloud VM; public server; federation hub; highly available |

## Hosted Production (Oracle Cloud) — Current Spend

Production stack runs on Oracle Cloud VM `<HOSTED_VM_IP>` (Portainer endpoint 5). Services in `docker-compose.hosted.yml`:

- `backend` — FastAPI API + Celery workers (AI gateway modules run in-process)
- `postgres` — PostgreSQL 17 + pgvector (`pgvector/pgvector:pg17`)
- `redis` — Celery broker/result backend
- `minio` — object storage
- `9router` — stack-local AI router on `:20128`
- `hub` — Community Garage federation hub (deploy config only; image lives in the private `autobrain-federation-hub` repo)
- `frontend` — static Flutter web on nginx-unprivileged `:8080`
- `dongle-server` — OBD2 dongle bridge
- `gh-runner` — in-VM GitHub Actions runner
- `backup` — scheduled backup/offsite agent

There is **no separate `ai` / `market-data` service** — see
[market-data.md](./market-data.md) for the current scraper story.

### Hardening posture (verified in compose)

| Service | Non-root | Read-only FS | Cap drop |
|---------|----------|--------------|----------|
| `frontend` | ✓ nginx-unprivileged (AUT-1188), port bound `127.0.0.1` only | ✓ | ✓ ALL |
| All others | image default user | — | — |

`ponytail:` only the frontend container is hardened this way. Extend
`user:`/`read_only`/`cap_drop` to backend, hub and 9router when their images
support it — not a cost item, a security-posture item owned by the Security
Officer.

### Estimated Monthly Costs (Oracle Cloud)

| Resource | Budget | Est. Actual | Notes |
|----------|--------|-------------|-------|
| VM Compute (ARM shape) | $50 AUD | $25–50 AUD | API, workers, 9Router, hub |
| Block Storage | $15 AUD | $5–10 AUD | PostgreSQL (incl. pgvector) + MinIO volumes |
| Network Egress | $20 AUD | $5–15 AUD | Variable by traffic |
| **Total** | **$85 AUD** | **~$35–75 AUD** | Within budget |

*Actual invoice amount is the source of truth — check Oracle Cloud Console billing before month-end close.*

## On-Prem Development (Hidden Costs)

The dev box at `<DEV_BOX_IP>` runs on local hardware — no cloud bill, but real cost:

| Resource | Est. Monthly | Notes |
|----------|--------------|-------|
| Electricity | $10–20 AUD | 24/7 availability |
| Hardware Depreciation | $15–30 AUD | Server amortised over 3 years |
| Network (residential) | $5–10 AUD | Static IP + bandwidth |
| Engineer time / maintenance | Unquantified | Reinstalls, upgrades, hardware failure |
| **Total** | **~$30–60 AUD + intangibles** | Not on any invoice |

**Note:** the same box also runs Demo/Default stacks (<PORTENER_HOST_IP>, Portainer endpoint 2) — those marginal costs are lower (no incremental hardware).

## Stack Components and Cost Drivers

| Component | Dev | Demo/Default | Hosted | Primary Cost Driver |
|-----------|-----|--------------|--------|--------------------|
| FastAPI backend | ✓ | ✓ | ✓ | CPU/RAM |
| Celery workers | ✓ | ✓ | ✓ | CPU (background AI jobs) |
| PostgreSQL 17 + pgvector | ✓ | ✓ | ✓ | Storage + RAM |
| Redis | ✓ | ✓ | ✓ | Memory (Celery broker) |
| MinIO | ✓ | ✓ | ✓ | Storage growth |
| AI gateway (12 modules, in backend) | ✓ | ✓ | ✓ | Network + 9Router tokens |
| 9Router (hosted-local) | remote | remote | ✓ | GPU/CPU inference on VM |
| Rego Lookup API (external service, own repo) | ✓ | ✓ | via `REGO_LOOKUP_URL` | CPU (deterministic) |
| Federation hub | — | — | ✓ | CPU + `hub.db` storage |
| Flutter web (static) | ✓ | ✓ | ✓ | nginx, negligible |
| Nginx (nginx-unprivileged, non-root) | ✓ | ✓ | ✓ | Minimal |
| OBD2 dongle server | ✓ | ✓ | ✓ | USB + CPU |
| GitHub Actions runner | ✓ | — | ✓ | CPU when jobs run |
| Backup agent | ✓ | ✓ | ✓ | CPU + offsite egress |

**ponytail:** per-service cost attribution is not currently measurable. Estimate from VM totals until Oracle Cloud per-VM/per-OCPU cost attribution is available.

## Finding the code

To trace where a cost driver lives in code, use the repo context graph rather
than grepping — see the Graft section in the root `AGENTS.md`
(`graft map` to orient, `graft ask "<cost question>"` to locate the code, `graft callers <symbol>` for the call graph).

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

## Related Finance Docs

- **[index.md](./index.md)** — Finance section index
- **[budget-tracking.md](./budget-tracking.md)** — budget allocation, revenue vs. cost, variance
- **[migration-budget.md](./migration-budget.md)** — Phase 3 Oracle Cloud migration cost case
- **[market-data.md](./market-data.md)** — scraper cost profile per tier
- **[fuel-servo-spy.md](./fuel-servo-spy.md)** — fuel feed keys and ingest cadence

## Sanitisation

This is a **public repo mirror** of the internal Finance wiki page. Instance IPs
are placeholders (`<HOSTED_VM_IP>`, `<DEV_BOX_IP>`, `<PORTENER_HOST_IP>`); real
host addresses and per-instance credentials live in the Outline
`Deployment & Infrastructure` section (internal only) and are never committed
here.

---

*Last updated: 2026-10-01 | Owner: CFO | Reviewed by: Documentation Manager (AUT-4397) | Sources: Oracle Cloud Console, Portainer, docker-compose.hosted.yml, migration cost case | Next review: 2026-11-01*