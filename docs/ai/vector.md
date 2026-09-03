# Vector Store Schema (pgvector)

AutoBrain uses PostgreSQL with the pgvector extension for semantic search. This document describes the schema, embedding pipeline, and search implementation.

## Extension

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Installed via the `pgvector/pgvector:pg17` image. No manual setup required.

## Columns

All embedding columns use `vector(1536)` to match OpenAI's `text-embedding-3-small` dimension.

| Table | Column | Content embedded | Purpose | Migration |
|-------|--------|------------------|---------|-----------|
| `diagnostics` | `embedding` | Symptoms + AI response summary | Semantic search for related diagnostics | `g7h8i9j0k1l2` |
| `service_records` | `embedding` | Description + notes + steps | Find similar service records | `g7h8i9j0k1l2` |
| `modifications` | `embedding` | Name + notes + category | Search modifications by description | `g7h8i9j0k1l2` |
| `receipts` | `embedding` | Vendor + extracted line-item names | Search receipts by content | `g7h8i9j0k1l2` |
| `social_issue_posts` | `embedding` | Title + body + tags | Search Community Garage help posts | `u1v2w3x4y5z6` |

`social_issue_posts.embedding` was added in the Issues Blog migration (`u1v2w3x4y5z6`) along with the rest of the `social_issue_*` tables. Its entity type in code is `issue` (see `_ENTITY_MAP["issue"]` in `backend/app/services/search.py`); the underlying table is `social_issue_posts`. `issue`-typed rows are community-visible (not scoped to a vehicle) and hidden posts (`status_hidden = true`) are excluded from search results.

## Index

```sql
CREATE INDEX ON diagnostics USING hnsw (embedding vector_cosine_ops);
```

HNSW (Hierarchical Navigable Small World) chosen over IVFFlat because:
- No training or list tuning required
- Better performance on small per-user tables
- Faster updates (no reindex needed)

Applied to all five embedding tables (the four above plus `social_issue_posts`): `g7h8i9j0k1l2` creates the index for the four user-scoped tables; `u1v2w3x4y5z6` creates it for `social_issue_posts`; `h1i2j3k4l5m6` rebuilds all indexes as HNSW on databases that originally applied them as IVFFlat.

## Embedding pipeline

### Embed-on-create

When a new entity is created, an embedding is generated via 9Router:

```python
# backend/app/services/search.py
embedding = await generate_embedding(entity_type, data)
```

For receipt OCR, embedding happens during `process_receipt` after extraction completes.

### Backfill

A scheduled Celery task `backfill_entity_embeddings` runs periodically to:
- Embed any entities missing embeddings
- Re-embed entities where source text changed

### Generation

Embeddings are generated via 9Router's OpenAI-compatible endpoint:

```
POST http://9router:20128/v1/embeddings
{
  "model": "text-embedding-3-small",
  "input": "<combined text from entity fields>"
}
```

If 9Router is unreachable, the entity is skipped and keyword-only search is used.

## Hybrid search

Search (`GET /api/v1/search?q=...&entity_types=...`) combines two strategies:

### 1. Keyword search (always runs)

ILIKE pattern matching against the entity's text fields. Returns results ranked by relevance score.

### 2. Vector search (optional)

When the query embedding can be generated, cosine similarity is computed:

```sql
SELECT id, 1 - (embedding <=> CAST(:query_embedding AS vector)) AS similarity
FROM diagnostics
WHERE user_id = :user_id
ORDER BY similarity DESC
LIMIT 20
```

The `<=>` operator computes cosine distance; `1 - distance` gives similarity.

### 3. Result merging

Results from both strategies are merged and deduplicated by entity ID. The final ranking combines keyword relevance and vector similarity scores.

If 9Router is unreachable or the embedding fails, search falls back to keyword-only mode — the platform never breaks.

## Query flow

```
User query → generate_embedding() → keyword search (ILIKE)
                                  → vector search (pgvector cosine)
                                  → merge + dedup + rank
                                  → return results
```

The query embedding is generated via 9Router. If the router is down, only keyword results are returned.

## Migration reference

| Migration | Description |
|-----------|-------------|
| `g7h8i9j0k1l2` | Add `embedding vector(1536)` columns + IVFFlat indexes on `diagnostics`, `service_records`, `modifications`, `receipts`. Installs the `vector` extension. |
| `u1v2w3x4y5z6` | Add `social_issue_posts` table + `embedding vector(1536)` column + HNSW index for the Community Garage Issues Blog. |
| `h1i2j3k4l5m6` | Rebuild all embedding indexes as HNSW (`vector_cosine_ops`) for small per-user tables — no list tuning or training pass required. |

## Fallback behaviour

- 9Router unreachable → keyword-only search
- Embedding generation fails → entity skipped, keyword-only
- pgvector extension missing → search endpoint returns empty results (no crash)
