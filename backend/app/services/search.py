"""Semantic search service — hybrid vector + keyword search across AutoBrain data."""

import asyncio

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.diagnostic import Diagnostic
from app.models.mod import Modification
from app.models.receipt import Receipt
from app.models.service import ServiceRecord
from app.services.vector_search import generate_embedding

logger = get_logger(__name__)

# Entity tables with their searchable columns and vector column mapping.
_ENTITY_MAP = {
    "diagnostic": {
        "model": Diagnostic,
        "columns": ["symptoms", "summary", "severity"],
        "vector_col": "embedding",
    },
    "service": {
        "model": ServiceRecord,
        "columns": ["description", "service_type", "notes", "workshop"],
        "vector_col": "embedding",
    },
    "modification": {
        "model": Modification,
        "columns": ["name", "category", "notes", "brand"],
        "vector_col": "embedding",
    },
    "receipt": {
        "model": Receipt,
        "columns": ["vendor", "original_name"],
        "vector_col": "embedding",
    },
}

# Valid entity types, exposed for input validation at the API boundary.
ENTITY_TYPES = tuple(_ENTITY_MAP.keys())


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input can't act as SQL patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_entity_types(types: list[str]) -> None:
    """Raise ValueError listing entity types that aren't in `ENTITY_TYPES`."""
    unknown = [t for t in types if t not in ENTITY_TYPES]
    if unknown:
        raise ValueError(f"Unknown entity types: {', '.join(unknown)}")


async def semantic_search(
    db: AsyncSession,
    query: str,
    vehicle_id: str | None = None,
    entity_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search across entities using hybrid keyword + vector similarity.

    Returns results ranked by combined score (keyword match weight + vector
    cosine similarity). Falls back to keyword-only if embeddings are
    unavailable.
    """
    types = entity_types or list(ENTITY_TYPES)
    results: list[dict] = []

    # Embedding is only needed for the vector phase — start it in the
    # background so keyword queries (which don't need it) run concurrently
    # instead of waiting on the embedding API call.
    embedding_task = asyncio.create_task(generate_embedding("query", {"symptoms": query}))

    for etype in types:
        cfg = _ENTITY_MAP[etype]
        model = cfg["model"]

        base_filters = []
        if vehicle_id:
            base_filters.append(model.vehicle_id == vehicle_id)

        # Keyword search (ILIKE on text columns) — always runs. `%`/`_` in the
        # query are escaped so user input can't act as SQL wildcards.
        escaped = _escape_like(query)
        keyword_conditions = []
        for col_name in cfg["columns"]:
            col = getattr(model, col_name, None)
            if col is not None:
                keyword_conditions.append(col.ilike(f"%{escaped}%", escape="\\"))

        keyword_stmt = (
            select(model)
            .where(and_(*base_filters, *keyword_conditions))
            .limit(limit)
        )
        keyword_rows = (await db.execute(keyword_stmt)).scalars().all()

        for row in keyword_rows:
            results.append(_serialise(etype, row, score=1.0, method="keyword"))

    embedding = await embedding_task

    # Vector search (cosine similarity) — runs if embedding available.
    if embedding is not None:
        for etype in types:
            cfg = _ENTITY_MAP[etype]
            model = cfg["model"]

            base_filters = []
            if vehicle_id:
                base_filters.append(model.vehicle_id == vehicle_id)

            vec_col = cfg["vector_col"]
            vec_filters = base_filters + [getattr(model, vec_col).isnot(None)]

            # PostgreSQL pgvector cosine distance: a <=> b
            embedding_literal = f"[{','.join(str(v) for v in embedding)}]"
            similarity_expr = text(f"{vec_col} <=> '{embedding_literal}'::vector")

            vec_stmt = (
                select(model, similarity_expr.label("distance"))
                .where(and_(*vec_filters))
                .order_by(similarity_expr)
                .limit(limit)
            )
            vec_rows = (await db.execute(vec_stmt)).all()

            for row, distance in vec_rows:
                score = 1.0 - distance  # cosine similarity
                # Skip if already found via keyword (dedupe).
                if any(r["id"] == row.id for r in results):
                    continue
                results.append(_serialise(etype, row, score=score, method="vector"))

    # Sort by score descending.
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def _serialise(etype: str, row, *, score: float, method: str) -> dict:
    """Convert a model row to a search result dict."""
    data = {
        "id": row.id,
        "type": etype,
        "score": round(score, 3),
        "method": method,
        "vehicle_id": row.vehicle_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

    if etype == "diagnostic":
        data.update({
            "symptoms": row.symptoms,
            "summary": row.summary,
            "severity": row.severity,
        })
    elif etype == "service":
        data.update({
            "description": row.description,
            "service_type": row.service_type,
            "workshop": row.workshop,
            "cost": row.cost,
        })
    elif etype == "modification":
        data.update({
            "name": row.name,
            "category": row.category,
            "brand": row.brand,
        })
    elif etype == "receipt":
        data.update({
            "vendor": row.vendor,
            "original_name": row.original_name,
            "total": row.total,
        })

    return data


async def backfill_entity_embedding(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
) -> bool:
    """Generate and store embedding for a single entity. Returns True on success."""
    cfg = _ENTITY_MAP.get(entity_type)
    if not cfg:
        return False

    model = cfg["model"]
    row = (await db.execute(select(model).where(model.id == entity_id))).scalar_one_or_none()
    if not row:
        return False

    data = _row_to_dict(row, entity_type)
    embedding = await generate_embedding(entity_type, data)
    if embedding is None:
        return False

    embedding_literal = f"[{','.join(str(v) for v in embedding)}]"
    table = model.__tablename__
    await db.execute(
        text(
            f"UPDATE {table} SET embedding = '{embedding_literal}'::vector WHERE id = :id"
        ),
        {"id": entity_id},
    )
    await db.commit()
    return True


def _row_to_dict(row, entity_type: str) -> dict:
    """Extract fields needed for embedding from a model row."""
    if entity_type == "diagnostic":
        return {
            "symptoms": row.symptoms,
            "ai_response": row.ai_response,
            "summary": row.summary,
            "severity": row.severity,
        }
    if entity_type == "service":
        return {
            "description": row.description,
            "service_type": row.service_type,
            "notes": row.notes,
            "workshop": row.workshop,
            "steps": row.steps,
        }
    if entity_type == "modification":
        return {
            "name": row.name,
            "category": row.category,
            "notes": row.notes,
            "brand": row.brand,
        }
    if entity_type == "receipt":
        return {
            "vendor": row.vendor,
            "original_name": row.original_name,
            "extracted": row.extracted,
        }
    return {}
