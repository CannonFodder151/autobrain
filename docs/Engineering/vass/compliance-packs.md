# VASS — Compliance Packs

**Status: not started.** Tracking AUT-3620 (generator, parent AUT-3608).

A compliance pack is the portable document a VASS engineer signs and an owner
hands to VicRoads. It is generated from a deterministic result, not authored.

## Pack sections

| Section | Source |
|---------|--------|
| Vehicle details | `vehicles` + the wizard's territory selection |
| Modification list | `modifications` for the vehicle |
| ADR / VSI / VSB6 reference per mod | `matched_rules[].standard_ref` from `POST /vass/check` |
| Compliance findings | `status`, `conditions`, `notes` per mod |
| Engineer sign-off fields | `engineers` + certification record |
| Owner declaration | account + vehicle identity |

## Output formats

| Format | Use |
|--------|-----|
| PDF | primary — the artefact an engineer signs |
| HTML | in-app review before download |
| JSON | API consumers; also the machine-readable form of the signed record |

## Requirements

- **Template per territory.** VIC first (VSI + VSB6 are VicRoads instruments),
  then NSW/QLD/SA/WA. The template set is the reason territory is a wizard step.
- **Signature placeholders**, not a signing service. A pack is a document an
  engineer signs with their own credentials; AutoBrain is not a certifying
  authority and must not imply it is.
- **Populate from the stored check.** Use `vas_checks` (the persisted audit
  record) rather than re-running the engine at export time, so the pack cites
  the verdict that was actually given. A re-run could produce a different answer
  after a rule edit and silently invalidate a signed document.

## Rendering engine

AUT-3620 names WeasyPrint or reportlab. WeasyPrint needs system libraries
(`pango`, `cairo`) in the backend image, which is currently `read_only` with
`cap_drop: [ALL]` — that is a container change, not a dependency bump. Weigh
that against reportlab's pure-Python footprint before choosing, and note the
pack has to render identically in the dev, prod and hosted images.

## Related

- [data-models.md](./data-models.md) — `vas_checks` is the pack's evidence
- [pre-check-wizard.md](./pre-check-wizard.md) — where territory is chosen