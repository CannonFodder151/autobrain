# VASS — Deterministic Rule Engine

Source: `backend/app/services/vass.py` (PR #743, **not merged**).

The engine answers `POST /vass/check` with no LLM call anywhere in the path. It
is a table lookup plus a status fold.

## Flow

```
mod_category ─► normalize_category()   ─┐
vehicle_class ─► normalize_vehicle_class() ─┤
                                           ▼
              SELECT * FROM vass_rules
                WHERE mod_category = :cat
                  AND vehicle_class  = :vclass
                  AND is_active = true
                                           │
                   no rows ──► CONDITIONAL + "manual engineering assessment recommended"
                                           │
                     rows ──► fold each rule.default_status into overall_status
                                           ▼
                              VASCheckResponse(status, matched_rules,
                                                applied_standards, conditions, notes)
```

## Normalisation

Free-text category and vehicle-class strings from the app are mapped onto the
enums before the query, because the query is an exact-match `AND` on both columns.
Two alias maps (100+ entries between them) absorb the vocabulary the Flutter app
and imports actually produce — `"susp"`, `"suspension"`, `"lowering"` →
`SUSPENSION`; `"car"`, `"passenger"`, `"ma"` → `PASS_CAR`.

An unrecognised string does **not** match any rule, so it surfaces as the
no-rows `CONDITIONAL` case rather than as a false `PASS`.

## Status fold

`overall_status` starts at `PASS` and degrades in priority order:

| Rule `default_status` | Effect on `overall_status` |
|-----------------------|---------------------------|
| `FAIL` | → `FAIL` (terminal — nothing overrides it) |
| `CONDITIONAL` | → `CONDITIONAL`, and its `conditions` are collected |
| `NOT_APPLICABLE` | → `NOT_APPLICABLE` only if the current status is still `PASS` |
| `PASS` | no change |

`FAIL` is absorbing: a later `NOT_APPLICABLE` cannot downgrade it back to
`PASS`. That is the intended severity ordering — one non-compliant rule fails the
check regardless of how permissive the others are.

`applied_standards` is the de-duplicated list of `standard_ref` values across all
matched rules, so a client can cite exactly which clauses were consulted.

## No-rules case

When nothing matches, the engine returns:

- `status: CONDITIONAL`
- `matched_rules: []`
- `applied_standards: []`
- a note naming the category and vehicle class that were looked up

This is a deliberate design choice: an unmatched query means the rules table has
a gap, not that the modification is legal. Returning `PASS` would make an
unseeded table indistinguishable from a compliant vehicle.

## What is deliberately absent

- No AI scoring, no severity weighting, no confidence score. AUT-3623 adds an AI
  layer *above* this result and must not alter `status`.
- No fuzzy matching on `mod_name`. Matching is exact after category/class
  normalisation only.
- No cross-rule interaction. Rules are evaluated independently and folded; a
  rule that depends on another rule's outcome is not expressible.

## Testing

Per AUT-3721 the acceptance bar is exact outcomes for 5 known
mod + vehicle-class combos, with unit tests covering every rule type. Note that
PR #743's summary claims syntax verification only — no test file for the engine
is included in the changed-file list.

## Related

- [data-models.md](./data-models.md) — the `vass_rules` rows being folded
- [standards-catalog.md](./standards-catalog.md) — what seeds those rows