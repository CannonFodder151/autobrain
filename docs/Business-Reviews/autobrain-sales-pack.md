# AutoBrain Sales Pack


> Mirror of the Outline doc *Business Reviews > AutoBrain Sales Pack*. Outline is the source of truth; keep this file in sync when the process changes.

Sales enablement for AutoBrain — an AI-powered car enthusiast companion sold as a hosted service, with a self-hostable MIT-licensed edition. All enquiries: **sales@autobrainservice.app**.

## Elevator pitch

> AutoBrain predicts vehicle issues before they become costly repairs. It tracks maintenance, fuel, diagnostics, parts and resale value, with an AI co-pilot that learns every vehicle — delivered as a hosted SaaS or run on your own hardware.

## Live URLs

| Asset | URL |
|-------|-----|
| Website | https://autobrainservice.app |
| Live demo | https://demo.autobrainservice.app |
| Web app | https://default.autobrainservice.app |
| GitHub | https://github.com/CannonFodder151/autobrain |

Demo login: `demo@autobrainservice.app` — password distributed on request via the Paperclip secret `demo/demo-account-password` (never published in this repo; read-only, sample data, no AI spend).

## Pricing

Paid plans include every feature including AI. The **Free** tier keeps core tracking (fuel, services, logbook, parts) but disables AI, file exports and rego lookup. Vehicle quotas are enforced per-account and adjustable by an admin (or the admin API).

| Tier | Price | Vehicles | AI / export / rego |
|------|-------|----------|--------------------|
| Free | $0    | 1        | Disabled           |
| Enthusiast | $9/mo | 1        | Included           |
| Garage | $19/mo | 5        | Included           |
| Club | Price on enquiry | Unlimited + dedicated deployment | Included           |

Upgrade path: Free / Enthusiast (1) → Garage (5) → Club (unlimited, dedicated).

## What it does

* **Predictive maintenance** — service logs, checklists, PDF/CSV export, AI next-service prediction from full history.
* **Fuel intelligence** — L/100km, cost/km, efficiency & cost graphs, AI insights.
* **AI diagnostics** — symptoms + OBD codes → causes, severity, parts, cost estimate; one tap to add to the next service.
* **Receipt & parts scanner** — OCR extracts parts, labour, cost and warranty; auto-adds to services and inventory.
* **Parts inventory** — quantities, usage tracking, AI reorder suggestions.
* **Resale value estimator** — value range, trend, recommendations.
* **Modification tracker** — AI performance/value impact, exportable build sheet.
* **Australian rego lookup** — AU plate + state → VIN/make/model/year/engine.
* **Analytics** — spend, total cost of ownership, cost/km, 12-month forecast.
* **ATO logbook** — per-trip logging (time, GPS, odometer, work/private) with per-financial-year exports for logbook claims (non club-registered vehicles).
* **Fuel receipts** — photo upload with AI parse of litres/price-per-litre and per-financial-year tax exports.
* **OBD-II** — fault-code library pushed straight into AI diagnostics; VIN auto-fill; admin-gated per account (Bluetooth adapter app in progress).
* **Backup & restore** — scheduled automated backups and full snapshot download/restore, admin-controlled.
* **Mobile apps** — Android app is **now in closed testing** (request early access via sales@autobrainservice.app); the **iOS app will be developed after Android reaches general availability**. The web app works on any device today.
* **Security** — MFA (TOTP), role-based access (admin/user), admin-only provisioning (no self sign-up).

## Why AutoBrain

* **AI everywhere, resilient** — every AI feature routes through the customer's own AI router with deterministic rule-based fallbacks; the platform never stops working when the model is down.
* **Trustworthy** — open-source (MIT), self-hostable, no vendor lock-in.
* **Australian-first** — real AU rego registry lookups and localised features.
* **Modern brand** — dark-first futuristic automotive UI (Tesla × NVIDIA × enterprise SaaS), brand kit in the AutoBrain design system.
* **Vector search (pgvector)** — PostgreSQL with pgvector extension for semantic search across vehicle data, parts, and diagnostics. Hosted on `pgvector/pgvector:pg17` image.
* **Non-root containers** — all services run as non-root user (`autobrain` uid 1000) with healthchecks; built for security and compliance.
* **Federated hub** — optional Community Garage social layer via `hub.autobrainservice.app`; servers opt in, Stripe billing runs on hub only; self-hosted instances pay $20/year/server to join.

## How to sell it

### Hosted (primary offer)

Walk the prospect through the live demo (5 vehicles, 6 years of data). Emphasise: no infrastructure to manage, backups included, admin-controlled vehicle quotas, upgrade path from Free/Enthusiast (1) → Garage (5) → Club (unlimited).

### Self-hosted (lead generator)

MIT-licensed Docker Compose stack. Four vCPUs + 8 GB RAM runs the full stack (backend, AI gateway, worker, Postgres with pgvector, Redis, MinIO, nginx). Point them at the GitHub README / website self-host section. These leads convert to support, onboarding or a dedicated Club deployment.

### Common objections

* "Is my data safe?" — MFA, role-based access, no self sign-up, self-host option.
* "What if the AI breaks?" — deterministic fallbacks keep everything working offline.
* "Why not build it myself?" — it's MIT-licensed; deploy your own, or pay us to run it.

## Contact & ownership

* Product owner / developer: Nathan Martina
* Sales inbox: sales@autobrainservice.app
* Notifications: no-reply@autobrainservice.app
* Repo: github.com/CannonFodder151/autobrain