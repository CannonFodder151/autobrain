# AutoBrain Database Schema

Managed by SQLAlchemy models (`backend/app/models/`) and Alembic migrations (`backend/alembic/`).

> **Migration heads:** the chain has a **single head** at `f7e8d9c0b1a2`
> (verified by `backend/tests/test_alembic_heads.py`). No merge migration is
> pending; `alembic upgrade head` applies cleanly.

## Vector search (pgvector)

PostgreSQL runs the `pgvector/pgvector:pg17` image (pgvector extension pre-installed; pinned by digest, AUT-1749).
For the pg16 → pg17 major-bump migration procedure, see `docs/Deployment-and-Infrastructure/server-migration.md`.
Embeddings are generated via 9Router's OpenAI-compatible `/v1/embeddings` endpoint (model: `text-embedding-3-small`, 1536-dim).
The following tables carry an `embedding vector(1536)` column (created by the
`g7h8i9j0k1l2` migration, HNSW index rebuilt by `h1i2j3k4l5m6`, and the fifth
table `social_issue_posts` added by `u1v2w3x4y5z6`) with HNSW
cosine-similarity indexes:

- **diagnostics** — symptoms + AI response summary
- **service_records** — description + notes + steps
- **modifications** — name + notes + category
- **receipts** — vendor + extracted line-item names
- **social_issue_posts** — title + body + tags (Issues Blog, AUT-627)

The `embedding` columns exist at the **database layer only** (raw SQL in the
migration) — the SQLAlchemy models do not map them, so writes go through raw
SQL (`backfill_entity_embedding` in `backend/app/services/search.py`).

See `docs/Engineering/ai/vector.md` for full schema, embedding pipeline, and hybrid search implementation.

Search is hybrid: keyword ILIKE runs always; vector cosine similarity layers on
top when the embedding router is reachable. Both paths return ranked results via
`GET /api/v1/search?q=...&entity_types=...` (`entity_types` is comma-separated).

## users

id (PK), email (unique), display_name, hashed_password (bcrypt), role (admin/user/demo), max_vehicles, is_active, free_account, obd_enabled, obd_auto_connect, mfa_secret, mfa_enabled, stripe_customer_id, stripe_subscription_id, stripe_subscription_status, stripe_price_id, created_at, updated_at.

`free_account` disables AI and rego lookup (file exports are available on all plans). `obd_enabled` / `obd_auto_connect` control OBD-II access (admin-granted). Stripe columns drive the hosted billing/licence state.

## vehicles

id (PK), user_id (FK), nickname, rego, vin, make, model, vehicle_type (car/motorcycle), colour, body_type, engine, transmission, year, odometer_km, condition, is_primary, club_reg, created_at, updated_at.

`vehicle_type` (default `car`) is enforced on add/edit before rego lookup and passed to the AI agents. `club_reg` (bool) — club-registered vehicles have the digital logbook disabled (product rule [PR-1](product-rules.md#pr-1--club-reg-disables-the-digital-logbook-victoria)).

## vehicle_shares

id (PK), vehicle_id (FK), invitee_user_id (FK users), status (pending/accepted), created_at.

Owner invites another account by email (must already be a user); the share stays `pending` until the invitee accepts. Pending invites grant no data access; only an accepted share makes the vehicle appear in the invitee's garage (owner's plan governs AI/rego entitlement on shared vehicles).

## vehicle_events

id, vehicle_id (FK), event_type (service/fuel/mod/diagnostic), title, occurred_on, odometer_km, amount, source_id, created_at.

## service_records

id, vehicle_id (FK), service_date, odometer_km, service_type, description, workshop, cost, currency, notes, ai_prediction, status (completed/scheduled), completed_date, next_due_km, next_due_date, steps (JSON), photo_keys (JSON), created_at.

## service_items

id, service_id (FK), part_id (FK, nullable), name, quantity, unit_cost, kind (part/labour/item), part_no, labour_hours, labour_rate.

## fuel_logs

id, vehicle_id (FK), fill_date, odometer_km, litres, price_per_litre, total_cost, is_full_tank, notes, distance_km, l_per_100km, cost_per_km, receipt_id (FK receipts), created_at.

Adding/editing a fill-up bumps the vehicle odometer unless a **newer** logbook trip governs.

## diagnostics

id, vehicle_id (FK), symptoms, ai_response (JSON), summary, severity, estimated_cost, parts_needed (JSON), added_to_service, linked_service_id (FK), status (open/resolved), resolved_at, created_at, embedding vector(1536).

Auto-resolves to `resolved` when the linked scheduled service is completed (green tick).

## modifications

id, vehicle_id (FK), name, category, brand, cost, install_date, odometer_km, notes, photo_keys (JSON), ai_impact (JSON), created_at, embedding vector(1536).

## parts

id, vehicle_id (FK), name, sku, category, quantity, min_quantity, unit_cost, supplier, location, notes, warranty_months, ai_reorder_suggestion, created_at, updated_at.

## part_movements

id, part_id (FK), delta, reason, service_id (FK), created_at.

## receipts

id, vehicle_id (FK), file_key (MinIO), original_name, content_type, ocr_status (pending/processing/done/failed), extracted (JSON), vendor, total, tax, currency, invoice_date, created_at, embedding vector(1536).

## extracted_items

id, receipt_id (FK), kind (part/labour), name, quantity, unit_cost, warranty_months, applied_to_service, created_at.

## valuation_snapshots

id, vehicle_id (FK), estimated_value, low, high, currency, factors (JSON), recommendations (JSON), created_at.

## market_listing_cache

id, make, model, year, source, listings (JSON), median_price, low_price, high_price, sample_size, fetched_at. UNIQUE(make, model, year). 24h cache of CarsGuide/CarSales market data feeding resale valuations (see market-data.md).

## sca_parts_cache

id, key (make|model|year), parts (JSON), category_count, fetched_at. UNIQUE(key). 24h cache of Supercheap Auto parts-guide lookups feeding inventory + AI suggested-service prefill (AUT-1792).

## notification_preferences

id, user_id (FK), vehicle_id (FK), push/email/discord_enabled, service_due_days, service_due_km, fuel_gap_km, discord_webhook_url, fcm_token, created_at, updated_at. UNIQUE(user_id, vehicle_id).

## notification_deliveries

id, vehicle_id (FK), kind, channels, sent_at. UNIQUE(vehicle_id, kind).

## logbook_entries

id, vehicle_id (FK), started_at, ended_at, start_odometer_km, end_odometer_km, distance_km, purpose (work/private), reason, start_location, end_location, start_lat, start_lng, end_lat, end_lng, start_photo_key, end_photo_key, status (in_progress/completed), created_at.

ATO logbook trips for non-club-reg vehicles only (rule [PR-1](product-rules.md#pr-1--club-reg-disables-the-digital-logbook-victoria)). Completing a trip updates the vehicle odometer.

## obd_codes

id, vehicle_id (FK), code, description, source (obd/manual), is_resolved, created_at.

Fault codes captured from a Bluetooth OBD2 adapter; pushed into the diagnostic AI tool.

## devices

id, user_id (FK), name, api_key_prefix, api_key_hash, vehicle_id (FK, nullable),
vehicle_type, last_seen_at, created_at.

Machine-to-machine API keys issued per user and optionally scoped to one vehicle.
Only `api_key_prefix` is stored in clear; the hash backs constant-time comparison.

## ha_integrations

id, user_id (FK), label, api_key_prefix, api_key_hash, vehicle_id (FK, nullable),
last_used_at, created_at.

Home Assistant integration keys (AUT-2541). Same prefix/hash shape as `devices`;
see [ADR 0026](./adr/0026-home-assistant-integration.md).

## passkey_credentials

id, user_id (FK), credential_id, public_key, sign_count, label, device_type,
transports, created_at, last_used_at.

WebAuthn registrations for passwordless login (AUT-3447). `UNIQUE(user_id, credential_id)`
enforced by migration `f7e8d9c0b1a2`.

## revoked_refresh_tokens

jti (PK), revoked_at, expires_at.

Denylist of refresh-token JTIs; checked on every refresh so a logged-out token
cannot be replayed before natural expiry.

## dongle_firmware

id, model, version, sha256, size_bytes, blob_key, release_notes, created_at.
UNIQUE(model, version). Firmware manifests for the OBD2 dongle (AUT-1673); the
binary lives in MinIO under `blob_key` and is served via signed URL.

## dongle_installed_firmware

device_id (PK), model (PK), firmware_version, serial_number, last_reported_at.

What each dongle reports it is running, so the backend can tell "needs update"
from "already current".

## engineers

id, display_name, email, phone, lat, lon, postcode, address, specialties (JSON),
certifications (JSON), years_experience, rating, review_count, price_per_hour,
price_per_job_min, price_per_job_max, availability (JSON), is_active,
is_verified, verification_status, embedding (vector), created_at, updated_at.

AutoBrain Shop engineer marketplace. Note `embedding` is a `Text` column (a
serialised float list), **not** a pgvector column — engineers are searched by
PostgreSQL full-text/filters, not cosine distance. It is therefore not one of the
five vectorised tables listed above.

## engineer_reviews

id, engineer_id (FK), user_id (FK), vehicle_id (FK, nullable), rating, title,
body, service_type, cost, created_at, updated_at.

Reviews left after an engineer job; feeds the marketplace `rating` aggregate.

## fuel_stations

id, source, source_id, brand, lat, lon, name, address, updated_at.
UNIQUE(source, source_id). Canonical station identity across fuel feeds.

## fuel_prices

id, station_id (FK), fuel_type, price, effective_at, source_id,
arbitration_score.

One current price per (station, fuel type, effective time). `arbitration_score`
records how confidently the arbitration layer picked this figure.

## fuel_price_snapshots

id, state, station_code, station_name, brand, address, latitude, longitude,
fuel_type, price, currency, updated_at, fetched_at, previous_price,
previous_price_at.

Append-only history per state, used by the fuel map, price-trend alerts and the
Servo Spy overlay. `previous_price*` makes trend deltas readable without a join.

## fuel_price_watchlist

id, user_id (FK), state, station_code, station_name, brand, fuel_type,
direction (up/down), threshold_pct, created_at.

Per-user "tell me when this station moves X%" rule (AUT-1859).

## fuel_price_poll_state

instance_id (PK), state (PK), last_poll_at.

Poll cadence bookkeeping so only one instance polls a given state (AUT-1813).

## fuel_price_arbitrations

id, station_id (FK), fuel_type, day, source_id, price, arbitration_score,
candidate_count, created_at.

One row per (station, fuel type, day) recording which feed won arbitration and
from how many candidates (AUT-2381/AUT-2386).
