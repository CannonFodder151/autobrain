# Finance

Budgets, costs, migration budget. Current stack: **PostgreSQL 17 + pgvector**, **non-root containers** (nginx-unprivileged on :8080, backend read-only + cap_drop), **federated hub** (Community Garage, AUT-333/AUT-532) running on Oracle Cloud ARM (Ampere A1).

## Document List

| Document | Purpose |
|----------|---------|
| [payments.md](./payments.md) | Stripe plans, pricing, billing flow, store-native IAP (sanitised) |
| [budgets-and-costs.md](./budgets-and-costs.md) | Company budget ($12k/mo), agent cost caps, infra spend tracking |
| [migration-budget.md](./migration-budget.md) | Oracle Cloud migration cost case (Phase 3) — Free Tier vs paid shapes |
| [fuel-pricing.md](./fuel-pricing.md) | 7-Eleven fuel prices (deterministic, no AI) |
| [fuel-servo-spy.md](./fuel-servo-spy.md) | Servo Spy fuel price map (premium-gated, WA/NSW/QLD feeds) |
| [market-data.md](./market-data.md) | CarsGuide/CarSales market data + valuations (deterministic-first) |

## Cross-references

- **Deployment & Infra** → [container-consolidation-migration.md](../Deployment-and-Infrastructure/container-consolidation-migration.md), [server-migration.md](../Deployment-and-Infrastructure/server-migration.md), [container-architecture.md](../Engineering/container-architecture.md)
- **Engineering** → [architecture.md](../Engineering/architecture.md), [ai-router-integration.md](../Engineering/ai-router-integration.md), [ai/vector.md](../Engineering/ai/vector.md) (pgvector)
- **Company** → [department-ownership-map.md](../Company/department-ownership-map.md) (Finance = CFO), [documentation-policy.md](../Company/documentation-policy.md)

---

*Sanitised public mirror. Internal-only content (secrets, keys, private links) lives in Outline (AutoBrain collection). Keep in sync per Documentation Policy.*