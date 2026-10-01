# VASS — Vehicle Approval & Modification Compliance

VASS answers one question deterministically: **is this modification legal on this
vehicle class under the relevant Australian standards?** No LLM is involved in the
core answer — rules are evaluated from a seeded standards table.

## Status

| Area | State | Tracking |
|------|-------|----------|
| Data models (`VASRule`, `VASCheck`) | Written, **not merged** | [PR #743](https://github.com/CannonFodder151/autobrain/pull/743) (open) |
| REST API (`/vass/check`, `/vass/rules`) | Written, **not merged** | [PR #743](https://github.com/CannonFodder151/autobrain/pull/743) (open) |
| Deterministic rule engine | Written, **not merged** | PR #743 — `backend/app/services/vass.py` |
| Alembic migration for `vass_rules` | **Missing** — PR #743 ships models with no migration | Follow-up required before merge |
| Rule seeding (ADR/VSI/VSB6 reference data) | Implemented | AUT-3723 |
| Flutter models + API client | Implemented | AUT-3755 |
| Pre-check wizard UI | Not started | AUT-3774 |
| Compliance results + PDF viewer | Not started | AUT-3776, AUT-3777 |
| Engineer marketplace screens | Not started | AUT-3778 |
| Import pathway tool | Not started | AUT-3779 |
| Settings (state/territory) | Not started | AUT-3780 |
| Regulatory corpus vector store | Not deployed | AUT-4039 (ChromaDB still absent from all compose files) |

**Nothing in `vass/` is on `main` yet.** This directory documents the design and
the current code state; treat the unmerged items as proposals.

## Documents

### Core

| Document | Purpose |
|----------|---------|
| [data-models.md](./data-models.md) | `VASRule` / `VASCheck` schema, enums, ADR/VSI/VSB6 taxonomy |
| [api.md](./api.md) | `POST /vass/check`, `GET /vass/rules`, rule CRUD |
| [rule-engine.md](./rule-engine.md) | Deterministic evaluation, alias normalisation, status aggregation |

### Regulatory data

| Document | Purpose |
|----------|---------|
| [standards-catalog.md](./standards-catalog.md) | ADR / VSI / VSB6 references and the rule-seeding contract |
| [vector-corpus.md](./vector-corpus.md) | Planned regulatory corpus vector store (blocked) |

### User-facing surfaces

| Document | Purpose |
|----------|---------|
| [pre-check-wizard.md](./pre-check-wizard.md) | Vehicle → mods → compliance wizard (Flutter, not started) |
| [compliance-packs.md](./compliance-packs.md) | PDF/HTML compliance packs for engineers and owners (not started) |

## Design rules

1. **Deterministic first.** `POST /vass/check` never calls 9Router. The rule
   engine is a pure function of `(mod_category, vehicle_class)` against the
   `vass_rules` table.
2. **Unknown is not compliant.** If no rule matches, the check returns
   `CONDITIONAL` with an explicit "manual engineering assessment recommended"
   note — it never silently returns `PASS`.
3. **AI is a fallback layer, not the judge.** [AUT-3623](/AUT/issues/AUT-3623)
   adds an AI explanation on top of a deterministic result. It can add prose; it
   cannot change `status`.
4. **Verdicts are recorded.** Each check is persisted to `vas_checks` so a
   compliance pack can cite what was actually evaluated.