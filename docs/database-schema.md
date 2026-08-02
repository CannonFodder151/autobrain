# Database Schema (PostgreSQL)

Managed by SQLAlchemy models (`backend/app/models/`) and Alembic
(`backend/alembic/`).

## users
| Column | Type | Notes |
|--------|------|-------|
| id | varchar(36) PK | uuid |
| email | varchar(255) UNIQUE | |
| display_name | varchar(120) | |
| hashed_password | varchar(255) | bcrypt |
| is_active | bool | |
| created_at / updated_at | timestamptz | |

## vehicles
| Column | Type | Notes |
|--------|------|-------|
| id | varchar(36) PK | |
| user_id | FK → users | index |
| nickname | varchar(120) | |
| rego | varchar(20) | index |
| vin | varchar(17) | |
| make / model / engine / transmission | varchar | |
| year | int | |
| odometer_km | int | |
| condition | varchar(20) | excellent/good/fair/poor |
| is_primary | bool | |

## vehicle_events (unified timeline)
id, vehicle_id FK, event_type (service/fuel/mod/diagnostic), title,
occurred_on date, odometer_km, amount, source_id.

## service_records
id, vehicle_id FK, service_date, odometer_km, service_type, description,
workshop, cost, currency, notes, ai_prediction, next_due_km, next_due_date.

## service_items
id, service_id FK, part_id FK (nullable), name, quantity, unit_cost,
labour_hours, labour_rate.

## fuel_logs
id, vehicle_id FK, fill_date, odometer_km, litres, price_per_litre,
total_cost, is_full_tank, notes, distance_km, l_per_100km, cost_per_km.

## diagnostics
id, vehicle_id FK, symptoms, ai_response (JSON), summary, severity,
estimated_cost, parts_needed (JSON), added_to_service, linked_service_id FK.

## modifications
id, vehicle_id FK, name, category, brand, cost, install_date, odometer_km,
notes, photo_keys (JSON), ai_impact (JSON).

## parts
id, vehicle_id FK, name, sku, category, quantity, min_quantity, unit_cost,
supplier, location, notes, warranty_months, ai_reorder_suggestion.

## part_movements
id, part_id FK, delta (in/out), reason, service_id FK, created_at.

## receipts
id, vehicle_id FK, file_key (MinIO), original_name, content_type,
ocr_status (pending/processing/done/failed), extracted (JSON), vendor,
total, tax, currency, invoice_date.

## extracted_items
id, receipt_id FK, kind (part/labour), name, quantity, unit_cost,
warranty_months, applied_to_service.

## valuation_snapshots
id, vehicle_id FK, estimated_value, low, high, currency, factors (JSON),
recommendations (JSON), created_at.
