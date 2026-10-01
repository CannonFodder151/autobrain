# AutoBrain Roadmap & Feature Plans

This document expands the roadmap preview in the Company section. AutoBrain is in **Phase 1 — Code Review & Improvement Initiative** (must complete before backlog work).

## Phase 0 — Setup (✅ Done)

- Company registered in Paperclip with agents, 9Router routing
- GitHub + Portainer awareness configured
- Core repos in scope: `autobrain` (monorepo), `autobrainservice-website`, `rego-lookup-api`
- Discord status/approval portal live
- Outline collection created

---

## Phase 1 — Code Review & Improvement (🔄 In Progress)

**Goal:** Reduce complexity, increase reliability, cut costs. Four parallel workstreams.

### Workstream 1: Container Reduction

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Audit current compose stacks (`docker-compose.hosted.yml`, `docker-compose.prod.yml`) | 🔄 | Deployment Lead | Count services, identify merge candidates |
| Merge redundant services (e.g., sidecars, proxies) | ⏳ | Deployment Lead | Target: ≥30% container count reduction |
| Remove unused volumes/networks | ⏳ | Deployment Lead | |
| Update Portainer stacks on Dev, Demo, Default, Hosted | ⏳ | Deployment Lead | |

### Workstream 2: Data Vectorisation

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Choose vector store (pgvector in PostgreSQL, or dedicated) | ⏳ | CTO / AI Gateway Engineer | Prefer native DB extension to reduce containers |
| Vectorise rego data, OBD codes, price history, petrol stations | ⏳ | AI Gateway Engineer | |
| Build embedding pipeline (batch + incremental) | ⏳ | AI Gateway Engineer | |
| Integrate vector search into deterministic lookup paths | ⏳ | AI Gateway Engineer | Target: <100ms p95 latency |

### Workstream 3: AI Function Reliability

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Inventory all AI functions in `ai/` gateway | 🔄 | AI Gateway Engineer | 5 modules to audit |
| Add deterministic fallback for each | ⏳ | AI Gateway Engineer | Rule-based first, AI fallback |
| Add evals for every AI path | ⏳ | QA & User Testing | Saved results, regression detection |
| Target: ≥50% reduction in AI calls | ⏳ | AI Gateway Engineer | Measure via 9Router metrics |

### Workstream 4: Modularity & Documentation Refresh

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Split mobile app into `autobrain-mobile` repo | 🔄 | Mobile Engineer | ADR-003 |
| Refactor backend into clear modules (API, domain, infra) | ⏳ | Founding Engineer | |
| Refresh all Company docs (this issue) | 🔄 | CEO / Doc Manager | Mission, Org Chart, Working Rules, Decisions, Roadmap |
| Refresh Engineering docs (architecture, API, DB, AI, OBD, mobile, onboarding, versioning) | ⏳ | CTO / Engineering | |
| Refresh Deployment docs (stacks, hosted/prod, backup, monitoring, per-instance secrets) | ⏳ | Deployment Lead | |
| Refresh Security docs (posture, secrets policy, incident runbooks, secret scan) | ⏳ | Security Officer | |
| Refresh Testing docs (strategy, QA logs, user testing results) | ⏳ | QA & User Testing | |
| Refresh Marketing docs (website, demo, social, growth) | ⏳ | CMO | |
| Refresh Finance docs (budgets, costs, migration budget) | ⏳ | CFO | |

---

## Phase 2 — Backlog (⏳ Pending)

Ship the product backlog once Phase 1 is complete. Backlog items tracked in Paperclip issues (auto-created from Discord `#feature-requests` / `#bug-reports`).

### High-Level Themes

| Theme | Example Features |
|-------|------------------|
| **Vehicle Intelligence** | OBD live data, fault code explanations, service predictions, recall lookup |
| **Regulatory & Compliance** | AU rego lookup (POST /lookup), state-specific rules, inspection reminders |
| **Cost & Fuel** | Petrol price map, fuel efficiency tracking, cost-per-km, charging station finder |
| **Community & Social** | Car meets, garage showcase, build threads, Q&A |
| **Platform** | Mobile app (offline-first), web dashboard, API for integrations, webhooks |

### Intake Process

1. Nathan/staff posts in `#feature-requests` or `#bug-reports` (staff-only)
2. n8n polls every 2 min → auto-creates Paperclip issue (feature → CTO, bug → Founding Engineer)
3. Agent picks up from queue — do NOT duplicate

---

## Phase 3 — Migration to Oracle Cloud (⏳ Pending)

Move hosted AutoBrain from on-prem to Oracle Cloud (ARM VM `152.69.188.133`, Portainer endpoint 5).

### Migration Workstream (Deployment Team Owns)

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Provision Oracle ARM VM (done) | ✅ | Deployment Lead | 152.69.188.133 |
| Deploy dedicated 9Router instance on Hosted | 🔄 | Deployment Lead | Separate from Default host |
| Deploy dedicated rego-lookup API on Hosted | 🔄 | Deployment Lead | |
| Migrate PostgreSQL + MinIO with zero downtime | ⏳ | Deployment Lead | |
| Migrate backend + AI gateway + frontend | ⏳ | Deployment Lead | |
| DNS cutover (Cloudflare → Nathan applies) | ⏳ | Deployment Lead → Nathan | No Cloudflare API key stored |
| HA validation (multi-AZ, backup, restore test) | ⏳ | Deployment Lead | |
| Post-migration QA sign-off | ⏳ | QA & User Testing | AUT-3624 |

---

## Cross-Cutting Concerns (All Phases)

| Concern | Approach |
|---------|----------|
| **Budget** | CEO reviews weekly. Hard stops via Paperclip budgets. |
| **Security** | Security Officer owns posture. Secrets in Paperclip/Outline only. Public repo scanned. |
| **Documentation** | Doc Manager audits for drift. Outline + GitHub mirror updated together. |
| **Testing** | QA owns test strategy. Post-deploy QA mandatory (AUT-3624). User testing logged to Outline. |
| **Incidents** | Deployment team triages. `#incidents` for active, `#updates` for resolution. |

---

## Feature Intake Channels (Discord → Paperclip)

- `#feature-requests` — staff-only, n8n → Paperclip issue → CTO
- `#bug-reports` — staff-only, n8n → Paperclip issue → Founding Engineer
- `#approvals` — board decisions only (budget, hires, contracts, major architecture, policy, incidents). **NOT for PRs.**

---

## Approval Gates

| Gate | Required | Auto-merges? |
|------|----------|--------------|
| PR merge | QA + Security + OCR | Yes (PR Gardener) |
| Budget > $500 | CEO + CFO (Nathan) | No |
| New hire | CEO (Nathan) | No |
| Contract/partner | CEO (Nathan) | No |
| Major architecture | CEO (Nathan) | No |
| Policy change | CEO (Nathan) | No |
| Incident response | Deployment Lead | N/A |

---

## Current Sprint Focus (Week of 2026-09-28)

1. **AUT-4045** — Company docs (Mission, Org Chart, Working Rules, Decisions, Roadmap) — CEO / Doc Manager
2. **AUT-4420** — Resolve recovery action blocking Doc Manager ownership — CEO
3. **AUT-3168** — Graft wiring for all AutoBrain repos — CTO / Engineering
4. **Container audit** — Deployment Lead
5. **AI function inventory** — AI Gateway Engineer

---

## Related

- [Mission & Vision](./mission-vision.md)
- [Org Chart](./org-chart.md)
- [Working Rules](./working-rules.md)
- [Decisions & ADRs](./decisions-adr.md)
- [Department Ownership Map](./department-ownership-map.md)
- [Documentation Policy](./documentation-policy.md)