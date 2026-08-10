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
