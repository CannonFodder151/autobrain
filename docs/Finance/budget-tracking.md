# AutoBrain Budget Tracking

Monthly budget allocation, spend tracking, and variance analysis for AutoBrain operations.

## Company Budget Overview

| Metric | Value |
|--------|-------|
| Monthly Revenue Target | $5,000 AUD |
| Monthly Infrastructure Budget | $500 AUD |
| Monthly Operational Budget | $2,000 AUD |
| Current Month Revenue | $0 AUD |
| Current Month Spend | $0 AUD |
| Runway | 12+ months |

*Source: Internal financial model; Stripe Dashboard for revenue; Oracle Cloud Console for infrastructure*

## Revenue Streams

| Stream | Monthly Recurring | Notes |
|--------|-------------------|-------|
| Enthusiast Monthly | $5.90 AUD/sub | Stripe: `autobrain-enthusiast-monthly` |
| Enthusiast Yearly | $59 AUD/sub | Stripe: `autobrain-enthusiast-yearly` |
| Garage Monthly | $11.90 AUD/sub | Stripe: `autobrain-garage-monthly` |
| Garage Yearly | $119 AUD/sub | Stripe: `autobrain-garage-yearly` |
| Early-Adopter (EARLY40) | Variable | 40% off first 3 months, capped at 100 redemptions |
| Mobile IAP | Same as web | Apple/Google take 15-30% |

## Cost Categories

| Category | Monthly Budget | Actual (Current) | Variance | Notes |
|----------|----------------|------------------|----------|-------|
| **Infrastructure** | | | | |
| Oracle Cloud VM (Production) | $75 AUD | $0 | - | AutoBrain-Hosted at <HOSTED_VM_IP> |
| Oracle Cloud Block Storage | $15 AUD | $0 | - | Database + MinIO |
| Oracle Cloud Network Egress | $20 AUD | $0 | - | Variable by traffic |
| On-Prem Dev Box | $60 AUD | $0 | - | Hidden costs (electricity, hardware) |
| **Operations** | | | | |
| 9Router AI Routing | $200 AUD | $0 | - | <INTERNAL_9ROUTER_URL> |
| Domain & SSL | $15 AUD | $0 | - | Cloudflare (managed) |
| Monitoring & Alerting | $50 AUD | $0 | - | Portainer, health checks |
| **Development** | | | | |
| Agent LLM Costs (Paperclip) | $1,200 AUD | $0 | - | Company budget: 1,200,000¢/mo |
| CI/CD (GitHub Actions) | $50 AUD | $0 | - | Included in GitHub plan |
| **Total** | **$1,685 AUD** | **$0 AUD** | **$0 AUD** | |

## Budget Enforcement

| Threshold | Action |
|-----------|--------|
| 50% of infra budget | Alert to `#ops` Discord |
| 75% of infra budget | CFO review required |
| 90% of infra budget | Freeze non-critical infra changes |
| 100% of infra budget | Hard stop — requires CEO approval to exceed |

## Tracking Process

### Weekly (Automated)
- Paperclip cost summary API polled weekly
- Results posted to `#ops` Discord via n8n webhook
- Format: category, spent, budget, % used, projection

### Mid-Month (Manual)
- CFO reviews spend vs. projection at day 15
- If any category > 70% at mid-month, escalate in `#approvals`

### Month-End Reconciliation
- Final spend locked at month close (UTC)
- Variance report generated (actual vs. budget)
- Carry-forward or clawback decisions documented
- Revenue vs. cost analysis posted to `#roadmap`

## Reporting Artifacts

- **Monthly Budget Report** — Outline page `Finance/Budget Tracking/YYYY-MM`
- **Revenue Dashboard** — Stripe Dashboard (live)
- **Infrastructure Dashboard** — Oracle Cloud Console + Portainer
- **Discord Digest** — Weekly post to `#ops` with summary table
- **Agent Workspace** — Paperclip cost dashboard (company + per-agent)

## Budget Change Request

To adjust a budget category:
1. CFO creates `#approvals` card with: category, current budget, requested budget, justification, duration
2. CEO approves/rejects via Paperclip interaction
3. On approval, CFO updates this document and notifies `#ops`

### Known Gaps
- **Revenue tracking**: Stripe webhook → internal dashboard not yet built
- **Per-feature cost allocation**: AI gateway, rego-lookup, fuel pricing costs not separated
- **Mobile IAP revenue**: Apple/Google reporting not integrated

## Integration Points

- **Stripe Dashboard** — Real-time subscription revenue (`dashboard.stripe.com`)
- **Oracle Cloud Console** — VM/metric billing for hosted environment
- **Paperclip Cost API** — `GET /api/companies/{id}/costs/summary`, `/by-agent`, `/by-project`
- **Portainer** — Container resource utilization (endpoint 5 = AutoBrain-Hosted)
- **9Router** — AI routing costs (tracked via Paperclip company budget)

---

*Last updated: 2026-09-26 | Owner: CFO | Review cadence: Monthly | Next review: 2026-10-26*