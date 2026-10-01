# VASS — API

Source: `backend/app/api/v1/vass.py` (PR #743, **not merged**). Router prefix
`/vass`, base URL `/api/v1`, registered in `backend/app/api/v1/__init__.py`.

## `POST /vass/check`

Deterministic compliance check. Auth: any logged-in user.

Request (`VASCheckRequest`):

| Field | Type | Notes |
|-------|------|-------|
| `mod_category` | string | free text; normalised by alias map |
| `mod_name` | string | the specific modification |
| `vehicle_class` | string | free text; normalised by alias map |
| `mod_description` | string \| null | optional prose carried into notes |

Response (`VASCheckResponse`):

| Field | Notes |
|-------|-------|
| `status` | `PASS` \| `FAIL` \| `CONDITIONAL` \| `NOT_APPLICABLE` |
| `matched_rules` | list of `{id, standard_ref, standard_section, standard_title, default_status, conditions, notes}` |
| `applied_standards` | de-duplicated standard refs, e.g. `["ADR 42/04", "VSB6 C.2.3"]` |
| `conditions` | collected conditions from every `CONDITIONAL` rule |
| `notes` | free text, incl. the "manual engineering assessment recommended" hint when nothing matched |
| `checked_at` | UTC timestamp |

No vehicle id is required — the check is on the *modification against a vehicle
class*, so it can run before a vehicle is selected. Persisted records go to
`vas_checks` keyed on `vehicle_id`; see [data-models.md](./data-models.md).

## `GET /vass/rules`

List rules, newest-standard-first (`ORDER BY standard_ref`).

| Query param | Notes |
|-------------|-------|
| `mod_category` | exact match after normalisation is **not** applied on list — filters the stored enum value |
| `vehicle_class` | same |
| `is_active` | defaults to `true`; pass `false` to list retired rules |

Returns `list[VASRuleOut]`. Auth: any logged-in user.

> The list endpoint filters on the raw stored value, while `/check` normalises
> aliases first. A client filtering with `"susp"` gets nothing; the same string
> works in `/check`. Worth aligning before merge.

## Rule CRUD (write scope)

| Method | Path | Scope | Notes |
|--------|------|-------|-------|
| POST   | `/vass/rules` | `require_write` | 201; rejects a duplicate (category, name, vehicle class) |
| PATCH  | `/vass/rules/{rule_id}` | `require_write` | partial update |
| DELETE | `/vass/rules/{rule_id}` | `require_write` | 204; hard delete, not a soft delete |

`GET /vass/rules` is read-scope, so a free-account user can inspect the rules
table. That is intentional — the rules are published standards, not user data.

## Entropy note for the client

`is_active=false` is honoured on the list route, but `DELETE` removes the row
outright. There is no undelete path. If seeded reference data must be auditable
over time, `VASCheck.rule_id` will dangle after a delete.

## Related

- [rule-engine.md](./rule-engine.md) — evaluation semantics
- [pre-check-wizard.md](./pre-check-wizard.md) — the Flutter consumer