# VASS — Pre-Check Wizard

**Status: not started.** Tracking AUT-3774 (selector + shell), AUT-3775
(modification checklist), AUT-3776 (results), AUT-3777 (PDF viewer),
AUT-3778 (engineer marketplace), AUT-3779 (import pathway), AUT-3780
(state/territory settings). Parent AUT-3626.

Flutter models and the API client already exist (AUT-3755, PR work on
`autobrain-mobile`); no screen is built.

## Wizard steps

| Step | Screen | Issue | Talks to |
|------|--------|-------|-----------|
| 1 | Vehicle selector — make/model/year, VIN scan | AUT-3774 | existing `/vehicles` routes |
| 2 | Territory — state/territory (determines ADR vs state rules) | AUT-3780 | `GET /vass/rules` |
| 3 | Modification checklist — add mods per category | AUT-3775 | `GET /vass/rules` to populate |
| 4 | Compliance results — per-mod verdict + inline citations | AUT-3776 | `POST /vass/check` |
| 5 | Export — PDF compliance pack | AUT-3777 | [compliance-packs.md](./compliance-packs.md) |

Step 2 exists because VSI and VSB6 are VicRoads instruments: the same
modification can be compliant in one state and not another. Territory is a
first-class input, not a settings afterthought.

## Why the checklist is not free-text

The engine matches on `mod_category` + `vehicle_class` after alias
normalisation, and `mod_name` is display-only. So step 3 must constrain the user
to real categories and known modification names — an invented `mod_name` still
evaluates correctly against its category's rules, but the result reads as
unfamiliar to a user who typed it.

## The results screen must show the citation

A `CONDITIONAL` with no citation is not actionable. The results screen
(AUT-3776) has to render `standard_ref` / `standard_section` / `conditions`
inline from the `matched_rules` payload, not just a coloured badge. The
"no rule found → CONDITIONAL" case needs distinct copy from a genuine
conditional, or users will read it as a soft pass.

## Related

- [api.md](./api.md) — the requests these screens make
- [rule-engine.md](./rule-engine.md) — what each verdict means