# Embedding Model Upgrade Procedure

## Current State

- **Model:** `openrouter/openai/text-embedding-3-small` (via 9Router)
- **Dimensions:** 1536
- **Provider:** 9Router (OpenAI-compatible `/embeddings` endpoint)
- **Storage:** PostgreSQL + pgvector (`vector(1536)` columns, HNSW indexes)
- **Tables:** `diagnostics`, `service_records`, `modifications`, `receipts`, `social_issue_posts`

## Upgrade Path

### 1. Choose New Model

Select a replacement embedding model. Common options:

| Model | Dimensions | Notes |
|-------|-----------|-------|
| `text-embedding-3-small` | 1536 | Current |
| `text-embedding-3-large` | 3072 | Higher quality, 2x storage |
| `text-embedding-v4` (Google) | 768 | Lower cost, lower storage |

### 2. Add New Column (Zero-Downtime)

```sql
-- Add new column alongside existing
ALTER TABLE diagnostics ADD COLUMN embedding_new vector(3072);
-- Repeat for each table

-- Create HNSW index on new column
CREATE INDEX idx_diagnostics_embedding_new ON diagnostics USING hnsw (embedding_new vector_cosine_ops);
```

### 3. Backfill

```python
# Run as Celery task or management command
from app.services.vector_search import generate_embedding

for table in ["diagnostics", "service_records", "modifications", "receipts", "social_issue_posts"]:
    backfill_embeddings(table, source_col="embedding", target_col="embedding_new")
```

### 4. Update Application Code

```python
# backend/app/services/vector_search.py
EMBEDDING_MODEL = "text-embedding-3-large"  # new model
EMBEDDING_DIMENSION = 3072  # new dimension

# Update _ENTITY_MAP and _to_text for new column
_ENTITY_MAP = {
    "diagnostics": {"table": "diagnostics", "embedding_col": "embedding_new", ...},
    ...
}
```

### 5. Verify

- [ ] Search returns relevant results
- [ ] Similarity scores are reasonable
- [ ] No regression in hybrid keyword+vector search
- [ ] Cache hit rate stable (if Redis caching enabled)

### 6. Cutover

```sql
-- Drop old column after validation
ALTER TABLE diagnostics DROP COLUMN embedding;
ALTER TABLE diagnostics RENAME COLUMN embedding_new TO embedding;
-- Repeat for each table

-- Reindex
REINDEX TABLE diagnostics;
```

### 7. Rollback

If issues detected:
```sql
-- Restore old column
ALTER TABLE diagnostics ADD COLUMN embedding vector(1536);
UPDATE diagnostics SET embedding = embedding_old;  -- from backup
-- Revert application code
```

## Configuration

### Environment Variables

```bash
# .env or Portainer stack env
EMBEDDING_MODEL=openrouter/openai/text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

### 9Router Configuration

The 9Router must support the new model. Update the router config:

```json
{
  "embeddings": {
    "model": "text-embedding-3-large",
    "dimensions": 3072
  }
}
```

## Related

- `docs/Engineering/ai/vector.md`: Vector store schema
- `backend/app/services/vector_search.py`: Embedding pipeline
- `backend/app/workers/tasks/embeddings.py`: Backfill task
- AUT-3168: Vector search implementation
