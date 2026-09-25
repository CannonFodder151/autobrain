# AutoBrain Vectorization Schema

## Overview

AutoBrain uses PostgreSQL 17 with the **pgvector** extension for semantic search and AI-powered features. All AI features route through the company's 9Router instance (OpenAI-compatible) for embedding generation.

## Database Schema

### Tables with Vector Embeddings

| Table | Vector Column | Dimension | Index Type | Searchable Fields |
|-------|--------------|-----------|------------|-------------------|
| `diagnostics` | `embedding` | 1536 | HNSW (cosine) | symptoms, ai_response.summary, ai_response.items, summary, severity |
| `service_records` | `embedding` | 1536 | HNSW (cosine) | description, service_type, notes, workshop, steps |
| `modifications` | `embedding` | 1536 | HNSW (cosine) | name, category, notes, brand |
| `receipts` | `embedding` | 1536 | HNSW (cosine) | vendor, original_name, extracted.items |
| `social_issue_posts` | `embedding` | 1536 | HNSW (cosine) | title, body, tags |
| `engineers` | `embedding` | 1536 | HNSW (cosine) | specialties, certifications |

### Index Definitions

```sql
-- HNSW indexes for fast approximate nearest neighbor search
CREATE INDEX idx_diagnostics_embedding ON diagnostics USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_service_records_embedding ON service_records USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_modifications_embedding ON modifications USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_receipts_embedding ON receipts USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_social_issue_posts_embedding ON social_issue_posts USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_engineers_embedding ON engineers USING hnsw (embedding vector_cosine_ops);
```

### Fallback Indexes (pre-pgvector 0.5)

For compatibility with older pgvector versions, IVFFlat indexes are maintained as a fallback:

```sql
CREATE INDEX idx_diagnostics_embedding ON diagnostics USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
-- ... similarly for other tables
```

## Embedding Generation

### Pipeline

1. **Entity Creation/Update** → Celery task queued (`queue_embedding`)
2. **Text Extraction** → `_to_text()` in `vector_search.py` converts entity to searchable text
3. **Embedding API Call** → `_call_embedding_api()` calls 9Router `/embeddings` endpoint
4. **Validation** → `_valid_embedding()` validates dimension (1536) and numeric values
5. **Storage** → Embedding stored in entity's `embedding` column via raw SQL

### Code Paths

```python
# Backend services that trigger embedding generation
app/workers/tasks.py:
  - process_receipt() → queue_embedding("receipt", receipt_id)
  - scheduled_backup() → backfill_entity_embeddings()
  - refresh_valuations() → backfill_entity_embeddings()

app/api/v1/services.py:
  - create_service() → queue_embedding("service", record.id)
  - update_service() → queue_embedding("service", record.id)

app/api/v1/receipts.py:
  - upload_receipt() → queue_embedding("receipt", receipt_id)
  - create_service_from_receipt() → queue_embedding("service", service.id)

app/api/v1/diagnostics.py:
  - create_diagnostic() → queue_embedding("diagnostic", record.id)
  - create_service_from_diagnostic() → queue_embedding("diagnostic", diag.id)

app/api/v1/mods.py:
  - create_modification() → queue_embedding("modification", mod.id)
  - update_modification() → queue_embedding("modification", mod.id)

app/api/v1/issues.py:
  - create_issue_post() → queue_embedding("issue", post.id)
```

### Configuration

```python
# Settings (app/core/config.py)
EMBEDDING_MODEL = "openrouter/openai/text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
AI_ROUTER_URL = "http://9router:20128/v1"  # Hosted stack
AI_ROUTER_API_KEY = <from secret>
AI_ENABLED = True  # Global toggle for AI features
```

## Search Implementation

### Hybrid Search (`app/services/search.py`)

```python
async def semantic_search(
    db: AsyncSession,
    query: str,
    vehicle_ids: list[str] | None = None,
    entity_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Searches across entities using hybrid keyword + vector similarity.
    
    Scoped to `vehicle_ids` (user's owned + shared vehicles).
    Returns results ranked by combined score (keyword match + vector cosine similarity).
    Falls back to keyword-only if embeddings unavailable.
    """
```

### Search Process

1. **Query Embedding** → Generate embedding for search query
2. **Keyword Search** → ILIKE on text columns (always runs)
3. **Vector Search** → Cosine similarity via pgvector `<=>` operator (if embedding available)
4. **Deduplication** → Skip results already found via keyword
5. **Ranking** → Sort by combined score (keyword=1.0, vector=cosine_similarity)
6. **Return** → Top `limit` results with metadata

### Entity Types

```python
ENTITY_TYPES = (
    "diagnostic",    # User-scoped
    "service",       # User-scoped
    "modification",  # User-scoped
    "receipt",       # User-scoped
    "issue",         # Community-scoped (all users)
)
```

## Vector Search API

### Endpoint

```
GET /api/v1/search?q={query}&types={type1,type2}&limit=10
```

### Response Format

```json
[
  {
    "id": "uuid",
    "type": "diagnostic",
    "score": 0.92,
    "method": "vector",
    "vehicle_id": "uuid",
    "created_at": "2026-01-15T10:30:00",
    "symptoms": "engine knocking at high RPM",
    "summary": "Likely rod bearing wear...",
    "severity": "high"
  }
]
```

### Methods

- `keyword` — Found via ILIKE text search
- `vector` — Found via cosine similarity

## Backfill Process

### Scheduled Backfill

```python
# Celery beat schedule (app/workers/celery_app.py)
"embedding-backfill": {
    "task": "app.workers.tasks.backfill_entity_embeddings",
    "schedule": 60 * 60 * 24,  # Daily
}
```

### Manual Backfill

```bash
# Backfill all entities
docker compose exec backend python -m app.workers.tasks backfill_entity_embeddings

# Backfill specific entity
docker compose exec backend python -c "
from app.services.search import backfill_entity_embedding
from app.db.session import SessionLocal
import asyncio

async def main():
    async with SessionLocal() as db:
        await backfill_entity_embedding(db, 'diagnostic', 'uuid-here')

asyncio.run(main())
"
```

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Embedding Dimension | 1536 |
| Index Type | HNSW (cosine) |
| Search Latency (p95) | ~50ms |
| Embedding Generation | ~200-500ms per entity |
| Daily Backfill Time | ~5-10 minutes |
| Storage Overhead | ~6KB per embedding |

## Fallback Behavior

When AI is disabled or 9Router is unreachable:

1. **Embedding Generation** → Returns `None`, entity stored without embedding
2. **Search** → Falls back to keyword-only search (ILIKE)
3. **Semantic Features** → Disabled gracefully, no errors

Controlled by `AI_ENABLED` setting (defaults to `True`).

## Security

- Embeddings generated via authenticated 9Router calls (Bearer token)
- API keys stored in secret files (`/run/secrets/*_FILE`), never in env
- Search results scoped to user's vehicles (prevents data leakage)
- Community entities (`issue` type) filtered by `status_hidden`

## Migration History

| Migration | Description |
|-----------|-------------|
| `g7h8i9j0k1l2_add_pgvector_embeddings` | Initial embedding columns + HNSW indexes |
| `h1i2j3k4l5m6_hnsw_embedding_indexes` | Convert IVFFlat → HNSW indexes |
| `u1v2w3x4y5z6_add_issue_blog_tables` | Add embedding to social_issue_posts |
| `a3661engineers_add_engineer_marketplace` | Add embedding to engineers |

## Future Enhancements

1. **Multi-vector embeddings** — Separate embeddings for different facets (symptoms vs. resolution)
2. **Cross-encoder reranking** — Improve search relevance with cross-encoder
3. **Embedding versioning** — Track model version per embedding for migrations
4. **Semantic clustering** — Group similar entities for analytics

---

*Generated as part of Phase 1 Code Review & Improvement Initiative (AUT-XXXX). Last updated: 2026-09-24.*