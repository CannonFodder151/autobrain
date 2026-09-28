# Budgets & Costs

**Company budget:** $12,000/month (1,200,000 cents) — set via Paperclip `budgetMonthlyCents` on the AutoBrain company (AUT-3032).

## Agent Budget Caps (Paperclip)

| Agent / Role | Monthly Cap | Enforcement |
|--------------|-------------|-------------|
| CEO | $2,000 | Soft alert at 80% |
| CTO / Founding Engineer | $3,000 | Soft alert at 80% |
| BDM | $1,000 | Soft alert at 80% |
| CMO | $1,500 | Soft alert at 80% |
| CFO | $500 | Soft alert at 80% |
| DevOps / Deployment Lead | $2,000 | Soft alert at 80% |
| QA & User Testing | $1,000 | Soft alert at 80% |
| Documentation Manager | $500 | Soft alert at 80% |
| Other / shared | $500 | — |

Caps are configured in Paperclip board → Company → Budgets. Cost events are recorded per agent run (9Router calls, API usage). Exceeding a cap triggers a Discord alert in `#ops` and marks the agent issue `needs_budget_review`.

## Infrastructure Spend (Monthly)

| Environment | Host / Cloud | Est. Monthly | Notes |
|-------------|--------------|--------------|-------|
| **Production (Hosted)** | Oracle Cloud VM `<HOSTED_VM_IP>` (ARM) | ~$37.50 | VM.Standard.A1.Flex 2 OCPU/12 GB + 100 GB block |
| **Demo + Default** | On-prem `<PORTENER_HOST_IP>` | ~$150-300 | Power/hw/colo; target for Free Tier migration |
| **Dev + Paperclip** | On-prem `<DEV_BOX_IP>` | ~$150-300 | Power/hw/colo; target for Free Tier migration |
| **NGINX-Host / HA** | Shared on-prem | Shared | Reverse proxy, Home Assistant |

**Total on-prem est.:** ~$300-600/mo (excl. labor, hardware depreciation)

## Cost Optimisation (Phase 1)

- **Container consolidation (AUT-3153):** merge standalone `worker` into `backend` → -1 container on hosted, reduces ARM resource pressure.
- **Vectorised data (pgvector):** single Postgres instance with `pgvector` extension replaces separate vector DB.
- **Deterministic-first AI (Phase 1c):** fuel prices, Servo Spy, market data, rego lookup all use fetch+parse; 9Router only for advice/trend fallback. Cuts 9Router spend ~60%.
- **Oracle Free Tier migration (Phase 3):** move Dev/Demo/Default/Paperclip/9Router to Always Free ARM VMs → $0 incremental.

## Stripe Billing Health

- **Live key:** `STRIPE_SECRET_KEY` secret (hosted stack env)
- **Webhook:** `POST /billing/webhook` → signature verified via `STRIPE_WEBHOOK_SECRET`
- **Health checks:** subscription active count, invoice.paid rate, failed payment rate, webhook 503 rate (billing endpoints return 503 until key is set)
- **Price IDs:** `scripts/stripe-setup.py` + `STRIPE_PRICE_*` env vars

## Monitoring & Alerts

- Paperclip cost dashboard → monthly spend vs budgets
- Discord `#ops` on cap breach
- Weekly digest in `#roadmap` includes spend summary
- Outline `Finance/Budgets & Costs` page synced from this doc

## Related docs

- [Payments & Subscription](./payments.md) — Stripe plans, billing health, IAP revenue
- [Infrastructure Costs](./infrastructure-costs.md) — per-environment spend, cost drivers, optimisation
- [Migration Budget](./migration-budget.md) — Phase 3 Oracle Cloud cost case
- [Market data](./market-data.md) — 9Router attribution: deterministic feeds cost ~$0, AI fallback is the spend

---

*Sanitised public mirror. Internal-only content (secrets, keys, private links) lives in Outline (AutoBrain collection). Keep in sync per Documentation Policy.*