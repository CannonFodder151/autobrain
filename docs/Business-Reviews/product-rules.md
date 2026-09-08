# Product Rules

Product rules are board/user decisions that constrain app behaviour. Each rule
has a stable id so code, tests, and docs can reference it across refactors.

## PR-1 — Club reg disables the digital logbook (Victoria)

**Status:** live (shipped 2026-08, AUT-177) · **Owner:** Nathan (board) · **Category:** legal/regulatory

### Rule

When a vehicle is marked **Club registration** (`vehicles.club_reg = true`), the
digital logbook feature must be disabled for that vehicle: no digital logbook
entries can be created or exported, and the logbook UI is hidden. Non-club-reg
vehicles keep the logbook feature unchanged.

### Why

In Victoria, vehicles on a **club permit** must keep the **physical VicRoads
club log book** (a paper booklet issued by VicRoads, with the club permit
attached to it). A digital app logbook cannot substitute, so using one for club
reg would put the owner out of compliance.

Official source (Transport Victoria / VicRoads, "Club permits" — club permit
rules): club permit holders must *keep a log book of their trips* and
*complete a log book entry every time you drive the vehicle more than 100
metres from its garage address*. The VicRoads club log book is a physical
document. Source issue: [AUT-90].

### Enforcement surfaces (keep in sync)

| Surface | Behaviour |
|---|---|
| Backend `backend/app/api/v1/logbook.py` `_require_logbook()` | `403` on POST (start trip), GET (list), GET `/stats`, PATCH (update/complete), GET `/export`, POST `/odometer-photo` for `club_reg` vehicles. DELETE stays open so stale entries can be removed. |
| Frontend `home_screen.dart` `_FeatureGrid` | Logbook tile hidden when `vehicle.clubReg`. |
| Frontend `add_vehicle_screen.dart` / `edit_vehicle_screen.dart` | "Club registration" checkbox subtitle explains the digital logbook is disabled (VIC physical-logbook requirement). |
| Tests `backend/tests/test_logbook_club_reg.py` | Club reg → 403 on create/list/stats/export; non-club reg unaffected; toggling club reg on blocks new entries. |

### History

- 2026-08-04 — initial implementation landed with the logbook feature (`club_reg`
  on the vehicle model, home-screen tile hidden, backend `_require_logbook` on
  write/export routes).
- 2026-08-10 — AUT-177: rule documented here; guard extended to read endpoints
  (list/stats/odometer-photo) for a consistent disable; user copy cites the VIC
  requirement; dedicated test added.

## PR-2 — Merch/commerce lives ONLY on autobrainservice.app, never in the app

**Status:** live (enforced 2026-08, AUT-1567; fully removed AUT-1571) · **Owner:** Nathan (board) · **Category:** commerce

### Rule

Merch/commerce lives ONLY on autobrainservice.app (autobrainservice-website
repo). Never add storefront, product listings, checkout, or order flows to the
app or backend API. The app and backend carry zero merch surface: no store
screen, no merch assets, no `/merch/*` routes, no `merch_orders` table, no
merch webhook handling. The AutoBrain Beanie and any future merchandise are
sold ONLY through the merch section of the **autobrainservice.app marketing
website**.

### Why

Board decision (Nathan): selling physical merch inside the product app mixes
storefronts, complicates fulfilment/shipping UX, and was explicitly rejected —
"it should only be on the autobrainservice.app website in the merch section".
Source issues: [AUT-1569], [AUT-1571].

### Enforcement surfaces (keep in sync)

| Surface | Behaviour |
|---|---|
| Backend `backend/app/api/v1/__init__.py` | No merch router registered; `/merch/*` routes must not exist. |
| Backend models/services/tests | No `app/models/merch.py`, no `app/services/merch.py`, no `test_merch.py`; `MerchOrder` model deleted. |
| Database | `merch_orders` table dropped by migration `o5n6p7q8r9s0`. |
| Billing webhook | `checkout.session.completed` handles subscription mode only; payment-mode sessions are ignored. |
| Frontend | No store screen, no Settings → Merch entry, no `assets/merch/` bundle. |

### History

- 2026-08 — AUT-1571: full removal — merch model/service/tests deleted,
  `merch_orders` table dropped, billing webhook payment branch removed.
  Supersedes the passive-table compromise of AUT-1567.
- 2026-08 — AUT-1567: beanie removed from app + backend sale API (was shipped as
  AUT-1540/AUT-1559); rule added with CI guard.
