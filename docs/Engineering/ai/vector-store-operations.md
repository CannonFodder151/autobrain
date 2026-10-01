# Vector Store Operations

Runbook for the pgvector store: what exists today, the `halfvec` target, the
regulatory corpus backfill, and how to upgrade the embedding model.

Companion to [vector.md](./vector.md) (schema reference for the user-data
embeddings). This doc covers **operations and the target design**.

> AUT-3927 marked this doc delivered, but it was never committed. Restored under
> AUT-4456 (Workstream B kickoff).

---

## 1. Current state on `main`

| Capability | Status | Where |
|-----------|--------|-------|
| pgvector extension enabled | Done | migration `g7h8i9j0k1l2` (`CREATE EXTENSION IF NOT EXISTS vector`) |
| pgvector-enabled Postgres image | Done | `pgvector/pgvector:pg17` in all three compose files |
| `vector(1536)` columns + HNSW index on user tables | Done | `g7h8i9j0k1l2`, `h1i2j3k4l5m6`, `u1v2w3x4y5z6` |
| Embedding **generation** (write path) | Done | `backend/app/services/vector_search.py` |
| Hybrid **read** path (keyword + vector, merged) | Done, general search only | `backend/app/services/search.py`, exposed at `GET /api/v1/search` |
| Daily backfill in Celery beat | Done, user entities only | `embedding-backfill` → `backfill_entity_embeddings` |
| `halfvec` storage | **Not started** | columns are full-precision `vector` |
| Regulatory corpus table | **Not started** | no such table exists |
| Domain query path reading the store | **Not started** | mod-legality (`ai/app/modules/mod_impact.py`) is a hardcoded lookup table + 9Router narrative; it never touches the vector store |

So the write path and the plumbing are done. What is missing is the **corpus**,
**half precision**, and **domain read paths**.

---

## 2. Why `halfvec`

Full-precision `vector(1536)` costs 4 bytes per dimension:

| | `vector(1536)` | `halfvec(1536)` | Saving |
|---|---|---|---|
| Column payload | 6,144 B | 3,072 B | 50% |
| HNSW index | ~2× payload | ~1× payload | ~50% |

Roughly 3 KB saved per row, plus the same again in the index. Corpus and user
tables are small today, so the saving is not yet the point — the point is that
**it makes the corpus affordable to grow** and it halves the in-memory working
set for HNSW traversal on the arm64 Hosted VM.

Recall cost of fp16 rounding on cosine distance is small enough that we accept
it for retrieval (not for anything that must be exact). Where exactness matters,
keep `vector`.

Requirements and caveats:

- `halfvec` needs **pgvector >= 0.7.0**. The pinned `pgvector/pgvector:pg17`
  satisfies this. If a future DB is provisioned without it, the migration fails
  loudly rather than silently degrading.
- You cannot change a column's type in place cheaply. Add `halfvec` alongside,
  backfill, then swap (see §5).
- **Do not** put a `halfvec` expression directly in an HNSW index against a
  `vector` column; index the `halfvec` column itself.

---

## 3. Target schema — regulatory corpus

The user-data embeddings (`diagnostics`, `service_records`, `modifications`,
`receipts`, `social_issue_posts`) answer "what did I do". The corpus table
answers "what does the law say" — the reference material used for mod-legality
and rego advice.

```sql
CREATE TABLE regulatory_documents (
    id            UUID PRIMARY KEY,
    -- Stable external identity, e.g. 'nsw-road-rules-2014-r271'.
    slug          TEXT NOT NULL UNIQUE,
    -- 'road_rules' | 'vehicle_standards' | 'rego' | 'modification_rules'
    corpus        TEXT NOT NULL,
    jurisdiction  TEXT NOT NULL,          -- 'AU' | 'AU-NSW' | 'AU-VIC' | ...
    title         TEXT NOT NULL,
    body          TEXT NOT NULL,          -- plain text, stripped of markup
    source_url    TEXT,
    source_version TEXT,                  -- e.g. '2014' — bumped when re-scraped
    content_hash  TEXT NOT NULL,          -- sha256(body); drives re-embed
    embedding     halfvec(1536),
    embedded_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pre-filter support: keyword pre-filter must be cheap and index-backed.
CREATE INDEX idx_regulatory_documents_corpus
    ON regulatory_documents (corpus, jurisdiction);

-- HNSW over the halfvec column.
CREATE INDEX idx_regulatory_documents_embedding
    ON regulatory_documents USING hnsw (embedding vector_cosine_ops);
```

Model in `backend/app/models/`, migration under `backend/alembic/versions/`.

`content_hash` is what makes the backfill idempotent: skip any row whose
`content_hash` matches the source and whose `embedding IS NOT NULL`.

---

## 4. Backfill

Celery task `backfill_regulatory_corpus`, registered in `celery_app.conf.beat_schedule`:

```python
"regulatory-corpus-backfill": {
    "task": "app.workers.tasks.backfill_regulatory_corpus",
    "schedule": crontab(hour=3, minute=0),   # off-peak, after fuel ingest at 02:00
},
```

Three phases, each independently restartable:

1. **Fetch** — refresh `body` + `content_hash` from the source. Bump
   `source_version`. Rows whose hash is unchanged are left alone.
2. **Embed** — for rows where `content_hash` changed or `embedding IS NULL`,
   chunk the body (~1200 chars, 150-char overlap), embed each chunk via 9Router,
   average the chunk vectors, L2-normalise, store into `embedding`.
3. **Verify** — report counts `{fetched, changed, embedded, skipped, failed}` and
   raise if `failed > 0` so the run shows up as failed rather than silently
   half-done.

Cost control: batch chunks into single 9Router calls (the endpoint takes an
`input` array). Do not embed on the request path.

Failure behaviour matches the rest of the platform: if 9Router is unreachable,
leave `embedding` NULL, log, and exit non-zero. Nothing breaks — the query path
falls back to keyword-only.

---

## 5. Embedding model upgrade

Changing `EMBEDDING_MODEL` or `EMBEDDING_DIMENSION` invalidates **every**
existing embedding. There is no partial state where old and new vectors can be
compared — cosine across two models is meaningless noise.

Runbook:

1. Add the new column (`embedding_v2 halfvec(N)`). Never mutate the old one.
2. Deploy with `EMBEDDING_MODEL` still set to the old value; dual-write both
   columns.
3. Run a one-off backfill task over the new column until `COUNT(*) WHERE
   embedding_v2 IS NULL` is 0.
4. Flip reads to `embedding_v2`, verify search relevance on a fixed query set.
5. Drop the old column + index.

Steps 1–3 are reversible: leave the old column in place until step 5 is
verified. If step 4 goes wrong, flip the read back without re-embedding anything.

---

## 6. Domain query path — keyword pre-filter, then vector

Acceptance criterion for Workstream B: **mod-legality reads the vector store,
with deterministic keyword match as the pre-filter.**

The ordering matters. Keyword first, vector second:

```sql
-- 1. Deterministic pre-filter: cheap, index-backed, always runs.
WITH candidates AS (
    SELECT id, slug, title, body,
           ts_rank(to_tsvector('english', title || ' ' || body), query) AS kw
    FROM regulatory_documents
    WHERE corpus = :corpus
      AND jurisdiction = ANY(:jurisdictions)
      AND to_tsvector('english', title || ' ' || body) @@ query
    ORDER BY kw DESC
    LIMIT 200
)
-- 2. Vector rank within the candidate set only.
SELECT id, slug, title,
       kw,
       1 - (embedding <=> CAST(:query_embedding AS halfvec)) AS similarity,
       (kw * :keyword_weight + (1 - (embedding <=> CAST(:query_embedding AS halfvec))) * :vector_weight) AS score
FROM candidates
WHERE embedding IS NOT NULL
ORDER BY score DESC
LIMIT 10;
```

Why pre-filter rather than parallel merge like `search.py`:

- The candidate set is index-backed and bounded, so HNSW traversal stays cheap
  as the corpus grows. A global vector scan does not.
- **A hit on the keyword filter is the deterministic answer.** A mod-legality
  answer with no keyword hit is not legal advice — it is a guess. Vector ranking
  only *orders* documents that already matched deterministically.
- Weights start at `keyword_weight = 0.6`, `vector_weight = 0.4`. Keyword-dominant
  on purpose. Tune from real queries, not from theory.

Fallback ladder when the vector leg is unavailable (9Router down, `embedding IS
NULL`, extension missing): return the keyword-ranked candidates **unweighted**.
The feature degrades, it does not break.

Wire-up: `ai/app/fallbacks/mod_impact.py` gains a `_mod_legality_docs(mod)` lookup
that queries `regulatory_documents` by mod name/category, and cites the matching
`slug` + `source_url` in the response. The `enhance()` narrative step stays as-is.

---

## 7. Verifying it works

```sql
-- extension
SELECT extname, extversion FROM pg_ext WHERE extname = 'vector';

-- column type is halfvec, not vector
SELECT table_name, column_name, udt_name
FROM information_schema.columns
WHERE udt_name IN ('vector', 'halfvec') ORDER BY table_name;

-- index present
SELECT indexname FROM pg_indexes WHERE indexname LIKE '%embedding%';

-- corpus coverage
SELECT count(*) AS total, count(embedding) AS embedded FROM regulatory_documents;
```

---

## 8. Operational notes

- **Backups.** `pg_dump` of the corpus is in the normal scheduled backup; the
  corpus is re-derivable from source, so it is the lowest-priority data in the
  database to restore.
- **Monitoring.** Watch `count(embedding)` vs `count(*)` on
  `regulatory_documents`; a gap means the backfill is failing silently.
- **Cost.** Every re-embed is a 9Router call. Do not re-embed on re-scrape when
  `content_hash` is unchanged.
- **Hosted.** Hosted is arm64. The pinned `pgvector/pgvector:pg17` digest is
  multi-arch, so the same migration runs on dev (x64) and Hosted (arm64)
  unchanged. Verify the extension is live on **both** before declaring the
  backfill healthy.
