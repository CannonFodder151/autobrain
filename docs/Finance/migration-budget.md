# AutoBrain Migration Budget — Phase 3

Phase 3 moves hosted AutoBrain services to Oracle Cloud. This document captures the cost case, budget allocation, and decision framework.

## Executive Summary

**Key Finding:** Production (AutoBrain-Hosted) is **already running on Oracle Cloud** at `152.69.188.133`. The migration scope is narrower than initially assumed:

1. Consolidate dev environment (decide: hybrid vs. full cloud)
2. Move marketing website (`autobrainservice-website`) to cloud
3. Move rego-lookup API (`rego-lookup-api`) to cloud (if separate)

## Current State

| Environment | Location | Status |
|-------------|----------|--------|
| Production API + Workers | Oracle Cloud VM | ✅ Running |
| Paperclip Control Plane (Hosted) | Oracle Cloud VM | ✅ Running |
| 9Router (Hosted) | Oracle Cloud VM | ✅ Running |
| Rego Lookup API | Unknown | 🔍 Audit needed |
| Marketing Website | Unknown | 🔍 Audit needed |
| Development Environment | On-prem (10.0.3.39) | ✅ Running |
| Demo / Default Stacks | On-prem (10.0.3.17) | ✅ Running |

## Cost Scenarios

### Option A: Hybrid (Recommended)
- **Production:** Stays on current Oracle Cloud VM
- **Development:** Stays on-prem (10.0.3.39)
- **Marketing + Rego-Lookup:** Move to hosted VM (if capacity allows)

| Cost Item | Monthly | Notes |
|-----------|---------|-------|
| Current Oracle VM | ~$35–75 AUD | No change |
| Additional services on same VM | $0 AUD | If capacity permits |
| On-prem dev box | ~$30–60 AUD | Hidden costs unchanged |
| **Total Incremental** | **$0 AUD** | |

**Pros:** Zero incremental cloud cost, local dev speed, no context switching
**Cons:** Two environments to maintain, manual sync between dev/prod

---

### Option B: Full Cloud Migration
- Move dev environment to Oracle Cloud
- May need second VM if current at capacity

| Cost Item | Monthly | Notes |
|-----------|---------|-------|
| Current Oracle VM | ~$35–75 AUD | |
| Second VM (dev) | ~$25–50 AUD | ARM shape, similar to prod |
| Block storage (dev) | ~$5–10 AUD | |
| Network egress (dev) | ~$5–15 AUD | |
| On-prem decommission | –$30–60 AUD | Savings from shutting down dev box |
| **Total Incremental** | **~$10–65 AUD/mo** | Net of on-prem savings |

**Pros:** Single environment, easier CI/CD, consistent infra
**Cons:** Higher cloud bill, dev latency, need to size VM correctly

---

### Option C: Cloud Dev + On-Prem Backup
- Primary dev on Oracle Cloud
- Keep on-prem as backup/fallback

| Cost Item | Monthly |
|-----------|---------|
| Current Oracle VM | ~$35–75 AUD |
| Second VM (dev) | ~$25–50 AUD |
| On-prem (idle/backup) | ~$10–20 AUD |
| **Total Incremental** | **~$35–70 AUD/mo** |

## Budget Allocation

| Phase | Budget | Status |
|-------|--------|--------|
| Phase 3 Migration Budget | **$0–$75 AUD/mo incremental** | Pending decision |
| One-time Migration Effort | Engineering time only | Deployment Lead owns |
| Contingency (3 months) | $0–$225 AUD | If Option B chosen |

**No additional budget request at this time.** Hybrid option requires $0 incremental spend.

## Decision Gate

**Owner:** CEO + CFO + Deployment Lead
**Target Decision:** Before Phase 3 kickoff

Required inputs:
1. [ ] Current Oracle VM utilization (CPU, RAM, disk, network) — Deployment Lead
2. [ ] Confirmation: which services already on hosted VM — Deployment Lead
3. [ ] Marketing site + rego-lookup current hosting — DevOps
4. [ ] Team preference: hybrid vs. full cloud — All leads

## Migration Tasks (Cost-Free)

These require engineering time only, no infrastructure spend:

- [ ] Audit current VM resources (Deployment Lead)
- [ ] Inventory all services and their current locations
- [ ] Document migration runbooks per service
- [ ] Test marketing site on hosted stack
- [ ] Test rego-lookup on hosted stack
- [ ] Update DNS (Cloudflare) via Deployment team → Nathan approval
- [ ] Validate end-to-end on hosted
- [ ] Decommission on-prem services (if Option B)

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| VM capacity insufficient for added services | Medium | Medium | Load test before migration; provision 2nd VM if needed |
| DNS cutover issues | Low | High | Staged rollout, rollback plan, Nathan approval via Discord |
| Data migration loss | Low | Critical | Backup → verify → migrate → verify; MinIO/PostgreSQL dumps |
| Dev team productivity drop | Medium (Option B) | Medium | Keep hybrid option as fallback |
| Cloud cost overruns | Medium | Medium | Monthly billing alerts; freeze infra if > 90% of budget |

## Approval Path

1. Deployment Lead completes audit (tasks above)
2. CFO presents cost comparison (this doc) to `#approvals`
3. CEO approves Option A / B / C via Paperclip interaction
4. On approval, Deployment Lead executes migration plan

---

*Last updated: 2026-09-26 | Owner: CFO + Deployment Lead | Source: migration-cost-case.md | Next review: Phase 3 kickoff*