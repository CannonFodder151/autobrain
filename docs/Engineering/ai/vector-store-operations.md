# Vector store operations

Operational runbooks for the pgvector-backed search store. Companion to [vector.md](vector.md) (schema) and [embedding-model-upgrade.md](embedding-model-upgrade.md) (model swap).

## Backfill embeddings

Task: `backfill_entity_embeddings` (Celery, `backend/app/workers/tasks.py`).
Runs periodically; embeds entities missing embeddings and re-embeds where source text changed. Idempotent.

Manual trigger (dev):
```bash
cd backend && celery -A app.workers.celery_app call app.workers.tasks.backfill_entity_embeddings
```
Monitor: `SELECT count(*) FROM <table> WHERE embedding IS NULL;` — should trend to 0.

## Halfvec migration (PoC — AUT-5872)

If storage reduction is needed, add `embedding_half halfvec(1536)` alongside `embedding`, backfill via `CAST(embedding AS halfvec)`, create HNSW index on `halfvec_cosine_ops`, verify search parity (`backend/tests/test_search*.py`), measure storage with `\dt+`. Keep both until parity confirmed; do not drop `vector` column until reads flipped and soaked.

## Model upgrade

See [embedding-model-upgrade.md](embedding-model-upgrade.md). Sequence: dual-write → backfill → flip reads → drop old.

## Health checks
- `SELECT extname FROM pg_extension WHERE extname='vector';`
- `SELECT count(*) FROM diagnostics WHERE embedding IS NULL;` (all five tables)
- Indexes: `\d diagnostics` → expect `hnsw` index on `embedding`.
- Search endpoint: `GET /api/v1/search?q=test` returns 200 even with 9Router down (keyword fallback).

## Rollback
Revert `EMBEDDING_DIMENSION` to prior value and redeploy; old column retained until step 4 of model upgrade.
