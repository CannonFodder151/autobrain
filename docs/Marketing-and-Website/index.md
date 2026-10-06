# Marketing & Website

Website, demo, social, growth.

## Document List

| Document | Purpose |
|----------|---------|
| [website.md](./website.md) | Website documentation (autobrainservice.app) |
| [demo-environment.md](./demo-environment.md) | Demo environment ops (demo.autobrainservice.app) |
| [social.md](./social.md) | Social media strategy & Buffer workflow |
| [social-image-generation.md](./social-image-generation.md) | Social image generation pipeline (deterministic-first) |
| [per-post-og-image-workflow.md](./per-post-og-image-workflow.md) | Per-post OG image workflow & author bio schema (AUT-3115) |
| [community-garage.md](./community-garage.md) | Community Garage feature docs (federated social, monetization) |
| [content-calendar.md](./content-calendar.md) | Marketing content calendar & approval gates |
| [phase1-social-calendar.md](./phase1-social-calendar.md) | Phase 1 launch social schedule (AUT-3972) |
| [growth-metrics.md](./growth-metrics.md) | Growth KPIs, funnel, Buffer analytics, reporting |

## Related Sections

- [Engineering](../Engineering/index.md) — architecture, database schema, AI modules
- [Deployment & Infrastructure](../Deployment-and-Infrastructure/index.md) — compose stacks, per-instance secrets
- [Company](../Company/index.md) — documentation policy, decisions
- [Business Reviews](../Business-Reviews/index.md) — sales pack, positioning claims

## Finding the code

Marketing facts are verified against the backend, not memory. Use the repo context graph (Graft — see the root `AGENTS.md`): `graft map` to orient, `graft ask "<question>"` to locate the code, `graft callers <symbol>` for the call graph, `graft grep "<literal>"` for an exhaustive search.

Reach for it before writing a claim. Buffer channel IDs, product-metric SQL, container counts, and module counts in this section have all been wrong at some point; `graft ask "buffer channels"` and a check against `backend/app/models/` catch that in seconds.

## Sync Policy

- **Source of truth:** Outline (AutoBrain collection, internal-only).
- **Mirror:** This `docs/Marketing-and-Website/` directory, public and sanitised.
- **Update rule:** Every Outline change → same-PR repo mirror update. Every repo change → Outline update (CMO agent). See [Documentation Policy](../Company/documentation-policy.md).
- Every metric, count, ID, and status in this section carries a source line at the bottom of its page. If a claim cannot be verified against the repo or a live API, it does not belong here.

## Sanitisation

Every page here is a **public mirror**. Instance IPs are placeholders, and per-instance credentials (Buffer org/channel IDs, Stripe keys, API keys, DB/MinIO secrets) are held in internal Outline — never in this repo. Read per-instance values from Buffer or the secrets store at use time rather than pasting them into docs.

Marketing copy is drafted here but **published only after the human CMO approves it in Discord `#marketing`** with the full publishable content inline. Approval gates live in [content-calendar.md](./content-calendar.md).

---

*Last updated: 2026-10-04 | Owner: CMO | Review cadence: Monthly | Next review: 2026-11-04*