# Roadmap

## Shipped (current — v0.4+)

### Core Vehicle Management
- Vehicle management with rego lookup, colour, body type, vehicle type (car/motorcycle)
- Rego lookup (8-state AU government scraper via rego-lookup-api, offline heuristic fallback)
- Vehicle sharing (invite by email, accept/deny, shared vehicle access)
- Club reg (digital logbook disabled for club-registered vehicles)

### Maintenance & Services
- Maintenance tracking with AI service prediction, PDF/CSV export
- Service intervals with reminders
- AI diagnostics (symptoms + OBD codes → causes, severity, parts, cost)
- OBD-II fault-code library with AI diagnostics integration
- OBD-II Bluetooth logging (Android RFCOMM, iOS BLE adapter) — in progress

### Fuel & Servo Spy
- Fuel tracker with L/100km, cost/km, efficiency graphs, AI insights, per-FY export
- **Servo Spy fuel map** — live fuel prices from WA FuelWatch, NSW FuelCheck, QLD Fuel Prices, VIC Servo Saver
  - Station map with markers, brand logos, price display
  - Favourite stations (servo-spy watchlist)
  - Price alerts (daily digest, configurable thresholds)
  - Cost per km and average fill cost projections (per vehicle)
  - Source arbitration (deterministic winner across overlapping feeds)
- 7-Eleven price lookup (projectzerothree.info)

### Valuation & Market Data
- **Used car valuation** — AI-powered resale estimator with market data (CarsGuide/CarSales)
- Market data scraper (self-hosted, cached 24h, vehicle-type routing)
- Valuation history with trend charts
- Live market search (cached 24h per query)

### Ownership Advisor (Premium)
- **Value** — market value with comparables and trade-in band (deterministic)
- **Replace** — replacement cost (used + new) with funding gap and monthly saving target
- **Upgrade** — next-tier options, similar vehicles, trade-up delta
- **Finance** — buy/finance/lease plans with amortization tables
- **Dream Car** — target lookup, affordability analysis, repayment estimates
- **AI Advisor** — reasons over the other modules via 9Router (deterministic fallback)
- **Car Check** — listing analysis with deal score, red/green flags (AI + deterministic)

### Receipts & Parts
- Receipt & parts OCR scanner
- Parts inventory with quantities, usage, AI reorder suggestions
- Parts SCA lookup (Supercheap Auto parts-guide by rego+state)
- Parts service prefill (AI-suggested parts for a service)

### Analytics & Reporting
- Analytics dashboard (fuel/service/mod spend, TCO, cost/km, forecast)
- ATO logbook with GPS, per-FY CSV export, dashboard-odometer OCR
- Profile export/import, admin backup & restore

### Social & Community
- **Community Garage** — share builds, leaderboards (shipped)

### Security & Auth
- Multi-factor authentication (TOTP)
- Self-service Free signup + Stripe billing (hosted)
- Device API keys (dongle devices for WiFi trip upload)

### Platform
- Flutter web + Android (Google Play)
- Docker Compose (dev, prod, hosted), Kubernetes manifests
- Home Assistant integration (vehicle data, service intervals, analytics)

## In progress

- Phase 1 code review & improvement initiative (see child issues AUT-2000..AUT-2004)
- Mobile app split into `autobrain-mobile` repo
- Reduce container count: consolidate beat into worker, merge AI gateway into backend image, fold worker+beat into the backend container (9 → 6 containers) — AUT-2000
- Vectorise data for efficient storage — AUT-2001 (schema documented in `docs/Engineering/ai/vector.md`)
- Make AI functions less AI-dependent (deterministic-first, AI fallback) — AUT-2002
- More modular code: extract shared utils, reduce cross-imports — AUT-2003
- Rewrite/refresh all documentation — AUT-2004

## Recently completed (Phase 1 documentation)

- Vector store schema documented in `docs/Engineering/ai/vector.md` (pgvector HNSW, hybrid search, fallback behaviour)
- Documentation index updated in `docs/index.md`

## Planned (short term)

- Service/maintenance reminders (push notifications)
- Discord webhook notifications
- Container health dashboard (Portainer integration)
- Offline-mode sync (mobile → server on reconnect)
- Hosted stack move to Oracle Cloud (Phase 3)

## Deferred / future

- Multi-user garage (shared vehicles across accounts)
- Insurance integration (quote estimates from vehicle data)
- Marketplace — list parts/mods for sale
- iOS App Store launch
- OpenTelemetry tracing
