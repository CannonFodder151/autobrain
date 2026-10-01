# VASS — Regulatory Corpus Vector Store

**Status: not deployed.** No ChromaDB service exists in any compose file, and
`ai/app/ingest_docs.py` does not exist. AUT-3631 was closed as done on the claim
that both existed; AUT-4039 reopened that gap and is blocked.

## What is planned

A semantic store over the primary regulatory sources — ADR texts, VSI bulletins,
VSB6 clauses, VicRoads guidelines — so a user can ask "is this allowed?" in
prose and get the relevant clause rather than only the table-driven verdict.

## Why it is separate from `vass_rules`

The deterministic engine must never depend on this. `vass_rules` is a small,
curated, verifiable table with an exact answer. A vector corpus is a
retrieval aid over long documents: it is probabilistic, it can cite the wrong
clause, and it cannot produce a compliance verdict.

The contract:

| Question | Answered by |
|----------|-------------|
| Is this mod legal on this vehicle class? | `vass_rules` via the deterministic engine |
| What does this clause actually say? | the regulatory corpus |

Conflating them would put a semantic search in the compliance path, which
breaks the deterministic-first rule the whole module is built on.

## Prerequisites before this is buildable

1. The `vass_rules` migration must land (currently missing from PR #743).
2. A decision on **pgvector vs ChromaDB**. The rest of AutoBrain already runs
   pgvector (`docs/Engineering/ai/vector.md`); a second vector store is a new
   container, a new backup path and a new failure mode. Reusing pgvector for the
   regulatory corpus keeps one embedding pipeline and one index type.
3. Corpus licensing. ADR, VSI and VSB6 texts are Commonwealth and VicRoads
   publications; confirm redistribution terms before ingesting them into a
   service users can query.

## Related

- [standards-catalog.md](./standards-catalog.md) — the verifiable citations this
  corpus must agree with
- AUT-4039, AUT-3631