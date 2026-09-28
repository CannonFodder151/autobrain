# Migration Budget — Oracle Cloud (Phase 3)

**Prepared by:** CFO (AutoBrain)
**Date:** 2026-09-28
**Status:** Draft for board review

---

## Executive Summary

AutoBrain production (Hosted) already runs on Oracle Cloud VM `152.69.188.133` (ARM Ampere A1). Phase 3 proposes migrating the remaining on-prem stacks (Dev, Demo, Default, Paperclip control plane, 9Router) to Oracle Cloud to consolidate infrastructure, reduce on-prem maintenance, and leverage Oracle's Always Free tier + flexible ARM shapes.

---

## Current Infrastructure Footprint

| Environment | Host | Purpose | Est. Monthly Cost (Power/HW/Colo) |
|-------------|------|---------|-----------------------------------|
| **Paperclip Control Plane + Dev Stack** | `<DEV_BOX_IP>` (on-prem) | Dev box, CI runners, Paperclip API, DB | ~$150-300 |
| **Demo + Default Stacks** | `<PORTENER_HOST_IP>` (Portainer-Host) | Demo (public), Default (staging), 9Router | ~$150-300 |
| **NGINX-Host / HomeAssistant** | Endpoints 3, 4 | Reverse proxy, HA | Shared |
| **Production (Hosted)** | `<HOSTED_VM_IP>` (Oracle ARM) | Production API, rego-lookup, 9Router | ~$50-100 (Oracle paid) |

**Total on-prem est. monthly:** ~$300-600 (excl. labor, hardware depreciation)

---

## Oracle Cloud Migration Options

### Option A: Oracle Cloud Always Free Tier (Recommended for Dev/Demo/Default)

| Resource | Free Tier Allowance | Suitability |
|----------|---------------------|-------------|
| Compute (ARM Ampere) | 4 OCPUs, 24 GB RAM | ✅ Dev + Demo + Default + Paperclip |
| Block Volume | 200 GB total | ✅ DB, MinIO, logs |
| Object Storage | 10 GB | ✅ Backups |
| Network | 10 TB/mo egress | ✅ All traffic |
| Load Balancer | 1 LB (10 Mbps) | ✅ Demo/Default ingress |

**Monthly cost:** **$0** (Always Free, no expiry)

**Constraints:** Resources shared across all Free Tier workloads. Sufficient for Dev/Demo/Default given current container count (AUT-3153 container consolidation reduces footprint).

---

### Option B: Paid ARM Flex Shapes (Production-scale / Guaranteed Resources)

| Shape | OCPUs | RAM | Est. Monthly (USD) | Use Case |
|-------|-------|-----|-------------------|----------|
| VM.Standard.A1.Flex | 2 | 12 GB | ~$35 | Paperclip control plane dedicated |
| VM.Standard.A1.Flex | 4 | 24 GB | ~$70 | Demo + Default consolidated |
| VM.Standard.A1.Flex | 4 | 24 GB | ~$70 | CI runners (self-hosted) |

**Total paid option:** ~$175/mo with dedicated resources, no Free Tier limits.

---

### Option C: Consolidate Everything on Existing Production VM

The production VM (`<HOSTED_VM_IP>`) currently runs only the Hosted stack. It has spare capacity.

| Action | Est. Monthly Delta |
|--------|-------------------|
| Add Dev/Demo/Default as additional stacks on same VM | $0 (within existing shape) |
| Upgrade shape if needed (e.g., 4→8 OCPU) | +$35-70/mo |

**Risk:** Production isolation. Not recommended until Phase 1 container consolidation (AUT-3153) proves resource headroom.

---

## Cost Comparison (Annual)

| Scenario | Year 1 | Year 2+ | Notes |
|----------|--------|---------|-------|
| **Status Quo (On-prem)** | $3,600-7,200 | $3,600-7,200 | Power, hardware replacement, admin time |
| **Option A: Free Tier Migration** | $0 | $0 | Requires ARM-compatible images (✅ already built) |
| **Option B: Paid Flex Shapes** | $2,100 | $2,100 | Predictable, dedicated resources |
| **Option C: Consolidate on Prod** | $0-840 | $0-840 | Lowest cost, highest blast radius |

---

## Migration Plan (Phase 3)

| Step | Description | Effort | Blockers |
|------|-------------|--------|----------|
| 1 | Provision Free Tier ARM VM for Dev + Paperclip | 1 day | None |
| 2 | Migrate Dev stack (docker-compose.dev.yml) | 1 day | Container consolidation (AUT-3153) |
| 3 | Migrate Demo + Default to 2nd Free Tier VM or same | 1 day | DNS cutover (Cloudflare) |
| 4 | Migrate 9Router to Oracle (or keep on Free Tier) | 0.5 day | 9Router is Go binary, ARM native |
| 5 | Decommission on-prem `<DEV_BOX_IP>`, `<PORTENER_HOST_IP>` | 0.5 day | — |
| 6 | Update CI runners to Oracle (gh-runner-autobrain-arm64) | 1 day | Runner registration |

**Total effort:** ~5 days engineering (Deployment Lead)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Free Tier resource contention | Medium | Dev/Demo slowdown | Monitor; upgrade to Flex if needed |
| ARM compatibility issues | Low | Build failures | Already building ARM images (build-hosted.yml) |
| Network latency (AU users) | Low | Slight API latency | Oracle Sydney region; same as current prod |
| Data migration (Postgres, MinIO) | Medium | Downtime | pg_dump/restore, mc mirror; schedule in maint window |
| Cloudflare DNS cutover | Low | Brief downtime | TTL reduction pre-cutover |

---

## Recommendation

**Proceed with Option A (Free Tier migration) for Dev, Demo, Default, Paperclip, 9Router.**

- **$0 incremental cost** vs ~$300-600/mo on-prem
- ARM images already validated in production (build-hosted.yml)
- Container consolidation (AUT-3153) reduces footprint further
- Production stays isolated on dedicated VM
- Reversible: on-prem hardware retained until 30-day burn-in

**Decision needed:** Board approval to initiate migration (AUT-3032 "Set company budgetMonthlyCents to 1200000" already reflects cloud budget headroom).

---

## Appendix: Current Oracle Spend

| Resource | Shape | Est. Monthly |
|----------|-------|--------------|
| Production VM (`<HOSTED_VM_IP>`) | VM.Standard.A1.Flex (2 OCPU, 12 GB) | ~$35 |
| Block Volume (100 GB) | — | ~$2.50 |
| **Total** | | **~$37.50/mo** |

Adding Free Tier VMs: **$0 additional**.

---

## Related docs

- [Budgets & Costs](./budgets-and-costs.md) — company budget, agent caps, current infra spend
- [Infrastructure Costs](./infrastructure-costs.md) — per-environment breakdown, cost optimisation
- [Deployment: Server Migration](../Deployment-and-Infrastructure/server-migration.md) — runbook for moving stacks
- [Deployment: Container Consolidation](../Deployment-and-Infrastructure/container-consolidation-migration.md) — Phase 1 prerequisite (reduces footprint)

---

*Sanitised public mirror. Internal-only content (secrets, keys, private links) lives in Outline (AutoBrain collection). Keep in sync per Documentation Policy.*