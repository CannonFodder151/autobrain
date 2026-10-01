# VASS — Standards Catalog

What seeds `vass_rules`, and the contract a new rule row has to satisfy.
Seeding tracked by AUT-3723.

## Standard sources

| Source | Reference format | Example | Authority |
|--------|------------------|---------|-----------|
| **ADR** — Australian Design Rules | `ADR <num>/<yy>` | `ADR 42/04` | Federal (DIT) |
| **VSI** — Vehicle Safety Information | `VSI <series>` | `VSI Advisory A1/2020` | VicRoads (VIC) |
| **VSB6** — Vehicle Safety Bulletin 6 | `VSB6 <chapter>.<clause>` | `VSB6 C.2.3` | VicRoads (VIC) |

ADR and VSI are carried as the `standard_type` enum. VSB6 is carried in
`standard_ref` as a clause string, because a VSB6 citation is always a specific
chapter+clause rather than a document-level reference.

## VSB6 chapter → modification category

| Chapter | Category | Subject |
|---------|----------|---------|
| A | `LIGHTING` | lighting and signalling |
| B | `BRAKING` | brakes |
| C | `SUSPENSION` | suspension and ride height |
| D | `ENGINE` | engine and drivetrain |
| E | `BODY` | body and structure |
| F | `IDENTIFICATION` | identification and compliance plates |
| G | `OTHER` | anything not covered above |

## Rule row contract

A row is only useful if all of these hold:

1. **`mod_category` + `mod_name` + `vehicle_class`** identifies exactly one
   evaluation target. The engine matches on category and vehicle class only;
   `mod_name` is stored for display and is **not** part of the match.
2. **`standard_ref` is verifiable.** Someone must be able to open the cited ADR
   part or VSB6 clause and confirm the verdict. No inferred or paraphrased
   references.
3. **`default_status` is the correct verdict for a compliant instance** of that
   mod on that vehicle class, per the cited clause.
4. **`conditions` is populated whenever `default_status = CONDITIONAL`** — it is
   what turns a conditional into a pass, so an empty `CONDITIONAL` rule is
   unactionable for the user.
5. **`is_active`** is true only while the reference is current. A superseded ADR
   part is retired, not deleted.

## Minimum seed coverage

AUT-3723 requires at least 10 real mod + vehicle-class combinations with an
integration test asserting the exact pass/fail for each. The named cases:

| Modification | Vehicle class |
|--------------|---------------|
| Turbo kit | passenger car |
| Lift kit | light truck |
| HID / LED conversion | heavy vehicle |

Three cases are specified; ten are required.

## Provenance

Cite the document revision the verdict was taken from in `standard_title` or
`notes` — a bare `ADR 42/04` gives a reader no way to know which amendment was
consulted. Where a VSI bulletin is time-limited, record the expiry in `notes` so
a stale row can be identified by reading the table.

## Related

- [data-models.md](./data-models.md) — the schema these rows land in
- [vector-corpus.md](./vector-corpus.md) — the planned full-text corpus behind
  these citations