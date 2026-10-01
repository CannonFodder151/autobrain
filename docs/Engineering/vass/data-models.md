# VASS — Data Models

Source: `backend/app/models/vass.py` (PR #743, **not merged**).

## Enums

### `VehicleClass`

Mirrors the ADR vehicle-classification letters. This is the axis a rule is
evaluated against, so a wrong class silently returns the wrong verdict.

| Value | ADR class |
|-------|-----------|
| `PASS_CAR` | MA — passenger car |
| `FORWARD_CONTROL` | MB — forward-control passenger vehicle |
| `OFF_ROAD_PASS` | MC — off-road passenger vehicle |
| `LIGHT_TRUCK` | NA — light truck / goods vehicle |
| `MEDIUM_TRUCK` | NB — medium truck |
| `HEAVY_TRUCK` | NC — heavy truck |
| `MOTORCYCLE` | LA/LB/LC/LD — motorcycle |
| `HEAVY_BUS` | MD — heavy bus |

### `StandardType`

| Value | Meaning |
|-------|---------|
| `ADR` | Australian Design Rules |
| `VSI` | Vehicle Safety Information (VicRoads bulletins) |

> VSB6 is referenced by **clause string** on `VASRule.standard_ref` (e.g.
> `VSB6 C.2.3`) rather than by enum. See [standards-catalog.md](./standards-catalog.md).

### `ModificationCategory`

Each maps to a VSB6 chapter.

| Value | VSB6 chapter |
|-------|--------------|
| `LIGHTING` | A |
| `BRAKING` | B |
| `SUSPENSION` | C |
| `ENGINE` | D |
| `BODY` | E |
| `IDENTIFICATION` | F |
| `OTHER` | G |

### `ComplianceStatus`

| Value | Meaning |
|-------|---------|
| `PASS` | Meets the standard as described |
| `FAIL` | Does not meet the standard |
| `CONDITIONAL` | Compliant only if stated conditions are satisfied, or no rule matched |
| `NOT_APPLICABLE` | The standard does not apply to this mod on this vehicle class |

## `VASRule` → table `vass_rules`

The seeded standards table. One row per (mod, vehicle class, standard clause).

| Column | Type | Notes |
|--------|------|-------|
| `id` | `String(36)` PK | uuid4 |
| `mod_category` | `Enum(ModificationCategory)` | |
| `mod_name` | `String(120)` | indexed; the specific modification, e.g. `turbo_kit` |
| `mod_description` | `Text` | nullable, human prose |
| `vehicle_class` | `Enum(VehicleClass)` | |
| `standard_type` | `Enum(StandardType)` | |
| `standard_ref` | `String(40)` | e.g. `ADR 42/04`, `VSB6 C.2.3` |
| `standard_section` | `String(80)` | nullable; specific clause |
| `standard_title` | `String(200)` | nullable |
| `default_status` | `Enum(ComplianceStatus)` | verdict when this rule matches |
| `conditions` | `Text` | nullable; JSON or prose conditions that make a `CONDITIONAL` a `PASS` |
| `notes` | `Text` | nullable |
| `is_active` | `bool` | indexed; soft delete via the admin API |
| `created_at` / `updated_at` | `timestamptz` | server default / on update |

## `VASCheck` → table `vas_checks`

An audit record of one evaluation. `status` is copied at evaluation time so a
later rule edit does not rewrite history.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `String(36)` PK | |
| `vehicle_id` | FK `vehicles.id` | indexed |
| `modification_id` | FK `modifications.id` | indexed, nullable (ad-hoc check with no saved mod) |
| `rule_id` | FK `vass_rules.id` | nullable — null when no rule matched |
| `mod_category` | `String(60)` | the normalised category actually used |
| `mod_name` | `String(120)` | |
| `vehicle_class` | `String(30)` | the normalised class actually used |
| `status` | `Enum(ComplianceStatus)` | |
| `applied_standards` | `Text` | JSON list of standard refs |
| `conditions_met` | `Text` | nullable |
| `notes` | `Text` | nullable |
| `created_at` | `timestamptz` | server default |

## Known gaps

- **No Alembic migration.** PR #743 adds both models but ships no migration
  under `backend/alembic/versions/`. `backend/tests/test_alembic_heads.py` only
  checks the graph, so this passes CI and fails at deploy with a missing table.
  Add a migration and extend the metadata smoke test before merging.
- **VASS tables are not in `database-schema.md`.** They are absent because the
  code is unmerged; this doc is the forward reference.

## Related

- [rule-engine.md](./rule-engine.md) — how these rows are evaluated
- [api.md](./api.md) — HTTP surface
- AUT-3720 (data models), AUT-3758 (vehicle classification)