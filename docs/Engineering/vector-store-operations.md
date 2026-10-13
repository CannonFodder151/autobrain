# Vector Store Operations (pgvector)

AutoBrain uses **PostgreSQL + pgvector** for semantic search across diagnostics, service records, modifications, receipts, and social issue posts. This document covers operational procedures: backfill, reindex, model upgrades, and storage optimization.

## Schema Overview

| Table | Embedding Column | Dimension | Index Type | Source Text |
|-------|------------------|-----------|------------|-------------|
| `diagnostics` | `embedding` | 1536 | HNSW | Symptoms + AI response |
| `service_records` | `embedding` | 1536 | HNSW | Description + notes + steps |
| `modifications` | `embedding` | 1536 | HNSW | Name + notes + category |
| `receipts` | `embedding` | 1536 | HNSW | Vendor + line-item names |
| `social_issue_posts` | `embedding` | 1536 | HNSW | Title + body |

**Current model:** `text-embedding-3-small` (1536 dim, float32) via 9Router/OpenRouter.

**Index:** HNSW (m=16, ef_construction=64) on all tables — optimal for per-user tables < 100k rows.

## Key Configuration

```python
# backend/app/core/config.py
EMBEDDING_DIMENSION: int = 1536
EMBEDDING_MODEL: str = "openrouter/openai/text-embedding-3-small"
```

The dimension is read from settings at migration apply time (via `settings.EMBEDDING_DIMENSION`), so changing it requires a new migration.

---

## Backfill Embeddings

### Full Backfill (all entities)

```bash
# On any host with DB access (dev box, hosted):
docker exec -it <backend-container> python -m app.workers.tasks backfill_entity_embeddings
```

### Incremental Backfill (specific entity type)

```python
# In Python REPL or script:
from app.workers.tasks import backfill_entity_embeddings
await backfill_entity_embeddings(entity_type="diagnostic", limit=1000)
```

### Backfill Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `entity_type` | `None` (all) | One of: `diagnostic`, `service`, `modification`, `receipt`, `issue` |
| `limit` | `None` (all) | Max rows to process |
| `batch_size` | `100` | Rows per embedding API call |
| `skip_existing` | `True` | Skip rows that already have an embedding |

### Monitoring Backfill Progress

```sql
-- Check embedding coverage per table
SELECT
  'diagnostics' AS table_name,
  COUNT(*) AS total,
  COUNT(embedding) AS with_embedding,
  ROUND(100.0 * COUNT(embedding) / COUNT(*), 1) AS pct
FROM diagnostics
UNION ALL
SELECT 'service_records', COUNT(*), COUNT(embedding), ROUND(100.0 * COUNT(embedding) / COUNT(*), 1) FROM service_records
UNION ALL
SELECT 'modifications', COUNT(*), COUNT(embedding), ROUND(100.0 * COUNT(embedding) / COUNT(*), 1) FROM modifications
UNION ALL
SELECT 'receipts', COUNT(*), COUNT(embedding), ROUND(100.0 * COUNT(embedding) / COUNT(*), 1) FROM receipts
UNION ALL
SELECT 'social_issue_posts', COUNT(*), COUNT(embedding), ROUND(100.0 * COUNT(embedding) / COUNT(*), 1) FROM social_issue_posts;
```

---

## Reindex (HNSW)

### Drop & Recreate Index (zero-downtime not guaranteed)

```sql
-- For each table:
DROP INDEX CONCURRENTLY IF EXISTS idx_diagnostics_embedding_hnsw;
CREATE INDEX idx_diagnostics_embedding_hnsw ON diagnostics USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

### Tune HNSW Parameters

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `m` | 16 | 4-64 | Higher = better recall, larger index, slower inserts |
| `ef_construction` | 64 | 32-256 | Higher = better recall, slower build |

```sql
-- Example: increase recall for large tables
CREATE INDEX idx_diagnostics_embedding_hnsw ON diagnostics USING hnsw (embedding vector_cosine_ops)
  WITH (m = 24, ef_construction = 128);
```

### Verify Index Health

```sql
-- Check index size
SELECT
  schemaname,
  tablename,
  indexname,
  pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE indexname LIKE '%embedding%';

-- Check index usage
SELECT * FROM pg_stat_user_indexes WHERE indexname LIKE '%embedding%';
```

---

## Model Upgrade Procedure

When a new embedding model is released (e.g., `text-embedding-3-large` at 3072 dim):

### 1. Add New Column (zero-downtime)

```sql
ALTER TABLE diagnostics ADD COLUMN embedding_new vector(3072);
ALTER TABLE service_records ADD COLUMN embedding_new vector(3072);
-- ... repeat for all 5 tables
```

### 2. Create New Index

```sql
CREATE INDEX CONCURRENTLY idx_diagnostics_embedding_new_hnsw
  ON diagnostics USING hnsw (embedding_new vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
-- ... repeat for all 5 tables
```

### 3. Backfill New Embeddings

```bash
# Temporarily point EMBEDDING_MODEL to new model, run backfill
# In production: deploy new backend with new model, run backfill task
docker exec -it <backend-container> python -m app.workers.tasks backfill_entity_embeddings
```

### 4. Switch Search to New Column

Update `vector_search.py` to use `embedding_new` column, deploy.

### 5. Drop Old Column (after validation)

```sql
-- After confirming search quality:
ALTER TABLE diagnostics DROP COLUMN embedding;
ALTER TABLE diagnostics RENAME COLUMN embedding_new TO embedding;
-- ... repeat for all 5 tables
DROP INDEX idx_diagnostics_embedding_hnsw;
ALTER INDEX idx_diagnostics_embedding_new_hnsw RENAME TO idx_diagnostics_embedding_hnsw;
```

### 6. Update Config

```python
# backend/app/core/config.py
EMBEDDING_DIMENSION = 3072  # New dimension
EMBEDDING_MODEL = "openrouter/openai/text-embedding-3-large"
```

---

## Storage Optimization: halfvec (float16)

### Current Storage

- 1536-dim float32 = 6 KB per row
- 50k rows ≈ 300 MB per table
- 5 tables ≈ 1.5 GB + indexes

### Migration to halfvec

```sql
-- 1. Add halfvec column (pgvector 0.7.0+ required)
ALTER TABLE diagnostics ADD COLUMN embedding_half halfvec(1536);

-- 2. Backfill from float32 column (automatic cast)
UPDATE diagnostics SET embedding_half = embedding::halfvec;

-- 3. Create HNSW index on halfvec
CREATE INDEX CONCURRENTLY idx_diagnostics_embedding_half_hnsw
  ON diagnostics USING hnsw (embedding_half halfvec_cosine_ops);

-- 4. Update vector_search.py to use embedding_half column
-- 5. Deploy, validate search quality

-- 6. Drop old column after validation
ALTER TABLE diagnostics DROP COLUMN embedding;
ALTER TABLE diagnostics RENAME COLUMN embedding_half TO embedding;
DROP INDEX idx_diagnostics_embedding_hnsw;
ALTER INDEX idx_diagnostics_embedding_half_hnsw RENAME TO idx_diagnostics_embedding_hnsw;
```

**Expected savings:** ~50% storage reduction (3 KB/row vs 6 KB/row).

### Binary Quantization (future)

For even smaller storage, pgvector supports binary quantization (1-bit per dimension):

```sql
-- Future: requires pgvector 0.8.0+
ALTER TABLE diagnostics ADD COLUMN embedding_bin bit(1536);
-- Custom quantization function needed
```

---

## Query Embedding Caching

Redis cache for query embeddings (TTL 1h) is implemented in `vector_search.py`:

```python
# backend/app/services/vector_search.py
_QUERY_CACHE_TTL = 3600
_QUERY_CACHE_PREFIX = "embedding:query:"

# On query embedding generation:
# 1. Normalize query text (lowercase, collapse whitespace)
# 2. SHA256 hash → cache key
# 3. Check Redis → return cached if valid
# 4. On miss: call 9Router, store in Redis, return
```

### Cache Stats

```bash
# Redis CLI
redis-cli --scan --pattern "embedding:query:*" | wc -l
redis-cli INFO memory | grep used_memory_human
```

---

## Search API

### Hybrid Search Endpoint

```
GET /api/v1/search?q=<query>&types=diagnostic,service&limit=10
```

**Parameters:**
- `q` — search query (required)
- `types` — comma-separated entity types (optional, default: all)
- `limit` — max results per type (default: 10, max: 50)

**Response:**
```json
{
  "results": [
    {
      "type": "diagnostic",
      "id": "uuid",
      "title": "Engine misfire on cold start",
      "score": 0.87,
      "metadata": { "severity": "high", "vehicle": "2018 Mazda CX-5" }
    }
  ]
}
```

### Per-Entity Weight Tuning (Planned)

Future: expose `vector_weight` and `keyword_weight` per entity type for hybrid search balancing.

---

## Troubleshooting

### Embedding Dimension Mismatch

**Error:** `ERROR: 22P02: invalid input syntax for type vector(1536)`

**Cause:** Router returned embedding with wrong dimension.

**Fix:**
1. Check `EMBEDDING_MODEL` matches `EMBEDDING_DIMENSION`
2. Verify router_utils.py `_valid_embedding()` validates dimension
3. Re-run backfill after fixing config

### Index Corruption / Slow Queries

```sql
-- Rebuild index
REINDEX INDEX CONCURRENTLY idx_diagnostics_embedding_hnsw;

-- Or drop/recreate with tuned params
```

### Search Returns No Results

1. Check embedding coverage (see backfill section)
2. Verify query embedding is generated (Redis cache hit/miss in logs)
3. Check `AI_ENABLED=true` and `AI_ROUTER_URL` reachable
4. Verify pgvector extension loaded: `SELECT * FROM pg_extension WHERE extname='vector';`

### Out of Memory During Index Build

- Reduce `m` and `ef_construction` parameters
- Build index during low-traffic window
- Consider partitioning large tables

---

## Related Files

| File | Purpose |
|------|---------|
| `backend/app/services/vector_search.py` | Embedding generation, caching, search |
| `backend/app/core/config.py` | `EMBEDDING_DIMENSION`, `EMBEDDING_MODEL` |
| `backend/app/workers/tasks.py` | `backfill_entity_embeddings` Celery task |
| `backend/app/api/v1/search.py` | `/api/v1/search` endpoint |
| `docs/Engineering/ai-models.md` | AI model documentation |