# Embedding model upgrade

See also: [vector.md](vector.md) (schema + pipeline) and `vector-store-operations.md` (operational checklist).

Upgrading `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` changes the vector type (`vector(N)`). 
Migrations must add a new column (pgvector does not allow altering type in place safely). 
Use dual-write → backfill → flip reads → drop old with soak.

## Prerequisites
- New model served by 9Router (`POST /v1/embeddings` returns new `embedding.length`).
- DB backup (`pg_dump`).
- `alembic heads` has single head (`backend/tests/test_alembic_heads.py`).
- Embedding tables: `diagnostics`, `service_records`, `modifications`, `receipts`, `social_issue_posts`.

## Steps

### 1) Dual-write
1. Alembic migration adds `embedding_new vector(<NEW_DIM>)` nullable + HNSW index on all five tables. Keep old `embedding` + index.
2. Set `EMBEDDING_DIMENSION_NEW=<NEW_DIM>` (opt-in). Keep `EMBEDDING_DIMENSION=<OLD_DIM>` until flip.
3. `backend/app/services/vector_search.py`: generate and `INSERT/UPDATE` both columns when `EMBEDDING_DIMENSION_NEW` set.

### 2) Backfill
Run `backfill_entity_embeddings` (Celery) or one-off task: re-embed source text with new model → write `embedding_new`. Batch 100, checkpoint `embedding_backfill_state` (table, last_id, done), idempotent. Verify zero nulls:
```sql
SELECT count(*) FILTER (WHERE embedding_new IS NULL) FROM diagnostics;
-- repeat for all five
```

### 3) Flip reads
1. Set `EMBEDDING_DIMENSION=<NEW_DIM>`, clear/ignore `EMBEDDING_DIMENSION_NEW`.
2. Switch reads/writes to `embedding_new` in `vector_search.py` (stop writing old). Deploy.
3. Verify `GET /api/v1/search` works; new entities embed correctly.

### 4) Drop old (after soak)
After ≥1 release cycle with no rollback: migration drops old `embedding` + index on all five, renames `embedding_new` → `embedding`, removes dual-write code/settings. Update dimension in docs.

## Rollback
Before step 4, revert `EMBEDDING_DIMENSION` to old value and redeploy — old column untouched.

## Config
`backend/app/core/config.py`: `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` (1536). Migrations read `settings.EMBEDDING_DIMENSION` at apply time so column dimension matches config.

## Implementation notes
- `generate_embedding` validates length == `EMBEDDING_DIMENSION`.
- Hybrid search in `backend/app/services/search.py` merges keyword + vector; falls back to keyword-only if 9Router/embedding fails.
