# Finance

Budgets, costs, migration budget.

## Document List

| Document | Purpose |
|----------|---------|
| [payments.md](./payments.md) | Stripe plans, pricing, billing flow (sanitised) |
| [budget-tracking.md](./budget-tracking.md) | Monthly budget allocation, revenue vs. cost, variance analysis |
| [infrastructure-costs.md](./infrastructure-costs.md) | Oracle Cloud + on-prem spend, per-service cost drivers |
| [migration-budget.md](./migration-budget.md) | Phase 3 Oracle Cloud migration cost case |
| [fuel-pricing.md](./fuel-pricing.md) | 7-Eleven fuel prices (deterministic, no AI) |
| [fuel-servo-spy.md](./fuel-servo-spy.md) | Servo Spy fuel price map (premium-gated) |
| [market-data.md](./market-data.md) | CarsGuide/CarSales market data + valuations |
| [petrol-price-map.md](../petrol-price-map.md) | Petrol price map (AUT-1813) — state feeds, cache, alerts |

## Related sections

- [Engineering](../Engineering/index.md) — architecture, API, database, AI modules
- [Deployment & Infrastructure](../Deployment-and-Infrastructure/index.md) — compose stacks, per-instance secrets

## Sanitisation

Every page here is a **public mirror**. Instance IPs are placeholders and
per-instance credentials (Stripe keys, fuel-feed partner keys, DB/MinIO
secrets) are held in the internal Outline `Deployment & Infrastructure` section
— never in this repo. See
[Documentation Policy](../Company/documentation-policy.md).