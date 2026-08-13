# AutoBrain API Specification

Base URL: `/api/v1`. Auth: `Authorization: Bearer <token>` (JWT). Interactive spec: `http://<host>/docs` (OpenAPI).

Access tiers: `role` ∈ `admin | user | demo`; `free_account` (per-user) disables **AI features and rego lookup** (403 on those endpoints). File exports are available on all plans. Demo accounts are read-only.

Vehicle sharing: a user with an accepted share on a vehicle can read and write its data. For shared vehicles, **AI and rego feature entitlement follows the owner's plan** — a free account invited to a paid owner's car gets the owner's features on that car.

## Auth

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/auth/login` | Login; returns `token_pair` or `{mfa_required, mfa_token}` when MFA enabled |
| GET    | `/auth/config` | Public client config: `{signup_enabled, mfa_enforced}` (drives the app's signup button) |
| GET    | `/version/mobile` | Public latest `autobrain-mobile` release (server-side GitHub check; `{repo, reachable, latest_version, html_url}`) |
| POST   | `/auth/mfa/verify` | Complete login with TOTP code |
| POST   | `/auth/refresh` | Refresh tokens |
| GET    | `/auth/me` | Current user (role, mfa_enabled, free_account, obd_enabled, obd_auto_connect, vehicle_count) |
| PATCH  | `/auth/settings` | Self-service toggles: `obd_auto_connect` (only this field — `free_account` is admin-managed) |
| GET    | `/auth/export` | Export your whole profile (user + vehicles + records) as JSON |
| POST   | `/auth/import` | Restore an exported profile **onto the logged-in account** (wipes that user's existing vehicles/records) |
| GET    | `/auth/mfa/setup` | Generate TOTP secret + QR |
| POST   | `/auth/mfa/setup-session` | Begin MFA setup (returns a session token) |
| POST   | `/auth/mfa/complete-setup` | Complete MFA setup with a verified code — returns a token pair |
| POST   | `/auth/mfa/enable` / `/auth/mfa/disable` | Verify code, enable/disable MFA |
| POST   | `/auth/password-reset/request` / `/confirm` | Email reset link / confirm |
| POST   | `/auth/signup` | Self-service Free-tier signup (display name + email; setup link emailed). **403 when `SELF_SIGNUP_ENABLED=false`** |
| POST   | `/auth/register` | **Admin-only** — create a user account |

## Admin users & server (admin role only)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/admin/users?q=` | List/search users |
| POST   | `/admin/users` | Create user (incl. free_account, obd_enabled, max_vehicles) |
| PATCH  | `/admin/users/{id}` | Update role/active/password/quota/free_account/obd_enabled |
| DELETE | `/admin/users/{id}` | Delete user |
| POST   | `/admin/users/{id}/re-upgrade` | Re-grant a paid tier to an account (default `enabled=true`) |
| GET    | `/admin/version` | Server version + GitHub latest-release check (up_to_date) |
| GET    | `/admin/backup` | Download full JSON database snapshot |
| POST   | `/admin/restore` | Upload a backup to wipe & restore the database (DANGEROUS) |

## Admin API (machine-to-machine, `X-Admin-API-Key` header, `ADMIN_API_KEY` env)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/admin-api/users` | List users |
| POST   | `/admin-api/users` | Create user (role, quota, free_account, obd_enabled, password/invite) |
| PATCH  | `/admin-api/users/{id}` | Update permissions (role, max_vehicles, free_account, obd_enabled, is_active, password) |
| POST   | `/admin-api/users/{id}/disable` | Disable an account |
| DELETE | `/admin-api/users/{id}` | Delete a user |
| GET    | `/admin-api/backup` | Download full JSON database snapshot (machine-to-machine) |
| POST   | `/admin-api/restore` | Wipe & restore the database from an uploaded backup (DANGEROUS) |

## Vehicles

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/vehicles` | List / create. List returns owned vehicles plus vehicles shared with you (`is_shared`, `shared_by` set on shared rows) |
| GET/PATCH/DELETE | `/vehicles/{id}` | Detail / update / delete. Shared users can read, but only the owner can update/delete |
| POST   | `/vehicles/rego-lookup` | Plate + state → VIN, make, model, year, engine. **Paid only**; pass optional `vehicle_id` to gate by that vehicle's owner (a shared free invitee inherits the owner's plan) |
| GET    | `/vehicles/{id}/timeline` | Unified event timeline |
| POST   | `/vehicles/{id}/shares` | Owner invites another account by email (creates a pending share) |
| GET    | `/vehicles/{id}/shares` | Owner lists shares (`pending`/`accepted`, invitee name + email) |
| GET    | `/vehicle-shares` | Invitee lists shares on them (`pending`/`accepted`, vehicle nickname + owner name) |
| POST   | `/vehicle-shares/{id}/accept` | Invitee accepts a pending share → vehicle appears in their garage |
| POST   | `/vehicle-shares/{id}/deny` | Invitee declines a pending share → share removed |
| DELETE | `/vehicle-shares/{id}` | Owner revokes access, or invitee removes a shared vehicle from their garage |

Sharing flow: the owner shares by email → the invitee sees a pending invite with **Accept/Deny** in the Vehicles screen → only after accepting does the car appear in their garage (labelled `Invited by <owner>`), and either party can later remove access. Pending invites grant no data access.

`club_reg: bool` — club-registered vehicles have the **digital logbook disabled** (product rule [PR-1](product-rules.md#pr-1--club-reg-disables-the-digital-logbook-victoria): Victoria requires the physical VicRoads club log book).

## Services (`/vehicles/{id}/services`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `` | List / create |
| GET/PATCH/DELETE | `/{service_id}` | Detail / edit (items replace + status) / delete |
| POST   | `/predict` | AI next-service prediction |
| GET    | `/export?fmt=csv\|pdf\|zip` | Export completed history; `zip` bundles the CSV with the receipt/scan images |

Completing a scheduled service created from a diagnostic auto-resolves (green-tick) that diagnostic.

## Fuel (`/vehicles/{id}/fuel`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `` | List / add fill-up (updates vehicle odometer unless a newer logbook trip exists) |
| PATCH/DELETE | `/{fuel_id}` | Edit / delete a fill-up |
| GET    | `/stats` | Totals, averages, series |
| GET    | `/export?fy=` | CSV export per Australian financial year (also accepts `fmt=zip`) |
| POST   | `/receipt?ai=true\|false` | Fuel receipt photo. `ai=true` OCR-fills litres & price/L then user enters odometer; `ai=false` stores photo only. |

## Logbook (`/vehicles/{id}/logbook`) — ATO claiming, non-club-reg vehicles only

Product rule [PR-1](product-rules.md#pr-1--club-reg-disables-the-digital-logbook-victoria): club-reg vehicles return `403` on every logbook route (create, list, stats, update, export, odometer-photo); only `DELETE` stays open for cleanup.

| Method | Path | Description |
|--------|------|-------------|
| POST   | `` | Start a trip (time/date, GPS location, odometer, work/private, reason) |
| GET    | `?fy=` | List trips per financial year |
| GET    | `/stats?fy=` | Trip / distance / work % totals |
| PATCH  | `/{entry_id}` | Edit trip; set end time/date/odometer to complete (updates the vehicle odometer) |
| GET    | `/{entry_id}` | Single trip incl. `gps_samples` route (list stays light — no samples) |
| DELETE | `/{entry_id}` | Delete a trip |
| GET    | `/export?fy=` | ATO logbook CSV per financial year |
| POST   | `/odometer-photo` | OCR a dashboard photo → odometer reading (AI, paid) |

Trips may carry a GPS route: `gps_samples` is a list of `{"t": <epoch seconds>, "lat": deg, "lon": deg}` points (WGS84) accepted on POST/PATCH. Invalid `0,0` (no-fix) and out-of-range points are dropped server-side (deterministic, no AI). The board CSV schema `epoch,...,lat,lon` (raw degrees x10^7) is accepted by `backend/app/services/trip_gps.py::parse_board_csv`.

## OBD-II (`/vehicles/{id}/obd`)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/settings` | `{enabled, auto_connect}` (access is admin-granted) |
| POST   | `/vin` | Auto-populate the VIN if missing |
| GET/POST | `/codes` | List / add fault codes |
| PATCH/DELETE | `/codes/{code_id}` | Update (resolve) / delete a code |

Code entries can be pushed into the diagnostic AI tool.

## Diagnostics (`/vehicles/{id}/diagnostics`)

| Method | Path | Description |
|--------|------|-------------|
| POST   | `` | Run AI diagnosis (symptoms + OBD codes). AI & paid only. |
| GET    | `` | List (incl. `status`: open/resolved) |
| POST   | `/{id}/add-to-service` | Queue as a scheduled service |
| POST   | `/{id}/resolve` | Mark resolved once fixed |
| DELETE | `/{id}` | Delete a diagnostic |

A diagnostic auto-flips to `resolved` when its linked service is completed.

## Mods, Receipts, Parts, Valuation, Analytics, Notifications

- **Mods** (`/vehicles/{id}/mods`): GET/POST, PATCH/DELETE `/{mod_id}`, POST `/impact` (AI), GET `/export?fmt=csv|pdf|zip`.
- **Receipts** (`/vehicles/{id}/receipts`): POST (multipart → async OCR), GET, POST `/{id}/apply-to-service`.
- **Parts** (`/vehicles/{id}/parts`): GET/POST, PATCH/DELETE `/{id}`, POST `/{id}/movement`, GET `/reorder-suggestions` (rule-based: flags parts at or below `min_quantity` — not AI).
- **Valuation** (`/vehicles/{id}/valuation`): POST (AI — disabled on free accounts), GET `/history`, GET `/market` (live CarsGuide/CarSales market data for the vehicle, cached 24h; `vehicle_type` routes cars vs motorcycles), GET `/market/search?q=` (search live listings across an arbitrary query, cached 24h). The estimate is anchored on the cached market median; when the user hasn't supplied a condition, it is inferred deterministically from diagnostics + service history (`condition` module) and surfaced in the response `factors` (`condition_estimate`, `condition_confidence`, `condition_score`, `condition_signals`).
- **Analytics** (`/vehicles/{id}/analytics`): GET (spend, TCO, cost/km, forecast, insights).
- **Notifications** (`/vehicles/{id}/notifications`): GET preferences, PUT update preferences (no `/test` endpoint).

## Billing (`/billing`) — hosted (Stripe)

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/checkout` | Create a Stripe Checkout session for a plan |
| GET    | `/pricing` | Public pricing (plans, early-adopter promo) |
| POST   | `/portal` | Open the customer billing portal |
| POST   | `/cancel` | Cancel the subscription |
| POST   | `/webhook` | Stripe webhook (subscription lifecycle) |

## Search

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/search?q=&entity_types=` | Hybrid search across diagnostics, services, modifications and receipts. Keyword ILIKE always runs; vector cosine similarity layers on top when the embedding router is reachable. `entity_types` is a comma-separated string (e.g. `diagnostic,service`); omit for all. |

## System

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/health` | Liveness |
| WS     | `/ws/{user_id}` | Live push (receipt.processed, etc.) |

## AI gateway (port 8001)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/health` | Liveness + router status |
| GET    | `/v1/modules` | List modules |
| POST   | `/v1/{module}` | Infer — `diagnostics`, `service-prediction`, `ocr`, `fuel-ocr`, `odometer`, `resale`, `mod-impact` |

All modules are deterministic (temperature 0) and validate/clamp numeric output (`resale` clamps low ≤ estimated ≤ high).
