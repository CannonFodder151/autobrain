"""Semantic search service — hybrid vector + keyword search across AutoBrain data."""

from sqlalchemy import TextClause, and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.device import Device
from app.models.diagnostic import Diagnostic
from app.models.fuel_station import FuelPrice
from app.models.market_listing import MarketListingCache
from app.models.mod import Modification
from app.models.receipt import Receipt
from app.models.service import ServiceRecord
from app.models.vehicle import Vehicle
from app.services.vector_search import generate_embedding
from app.social.models import SocialIssuePost

logger = get_logger(__name__)

# Entity tables with their searchable columns and vector column mapping.
# `community: True` marks entities that are visible to every user (NOT scoped
# to the requesting user's vehicles) and whose rows have a status_hidden flag.
# `vehicle_id_col` overrides the column used for vehicle-scoping (default
# `vehicle_id`); "id" means the entity IS the vehicle.
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
    "issue": {
        "model": SocialIssuePost,
        "columns": ["title", "body"],
        "vector_col": "embedding",
        "community": True,
    },
    "fuel_price": {
        "model": FuelPrice,
        "columns": ["fuel_type"],
        "vector_col": "embedding",
        "community": True,
    },
    "device": {
        "model": Device,
        "columns": ["name"],
        "vector_col": "embedding",
    },
    "market_listing": {
        "model": MarketListingCache,
        "columns": ["make", "model"],
        "vector_col": "embedding",
        "community": True,
    },
    "vehicle": {
        "model": Vehicle,
        "columns": ["nickname", "make", "model", "rego"],
        "vector_col": "embedding",
        "vehicle_id_col": "id",
    },
}

# Valid entity types, exposed for input validation at the API boundary.
ENTITY_TYPES = tuple(_ENTITY_MAP.keys())


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input can't act as SQL patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def semantic_search(
    db: AsyncSession,
    query: str,
    vehicle_ids: list[str] | None = None,
    entity_types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search across entities using hybrid keyword + vector similarity.

    Scoped to `vehicle_ids` (the requesting user's owned + shared vehicles);
    pass an empty list to deny all rows, or None to skip scoping (internal use).

    Returns results ranked by combined score (keyword match weight + vector
    cosine similarity). Falls back to keyword-only if embeddings are
    unavailable.
    """
    types = list(entity_types) if entity_types is not None else list(_ENTITY_MAP.keys())
    results: list[dict] = []

    # Try vector search first (needs embedding for the query text).
    embedding = await generate_embedding("query", {"symptoms": query})

    for etype in types:
        cfg = _ENTITY_MAP[etype]
        model = cfg["model"]

        base_filters = []
        if vehicle_ids is not None and not cfg.get("community"):
            fk_col = cfg.get("vehicle_id_col", "vehicle_id")
            col = getattr(model, fk_col, None)
            if col is not None:
                base_filters.append(col.in_(vehicle_ids))
        if cfg.get("community"):
            # Hidden/modded posts must never surface in search.
            if hasattr(model, "status_hidden"):
                base_filters.append(model.status_hidden.is_(False))

        # Keyword search (ILIKE on text columns) — always runs. Columns are
        # OR-ed (match any column); vehicle scope stays AND-ed. `%`/`_` in the
        # query are escaped so user input can't act as SQL wildcards.
        escaped = _escape_like(query)
        keyword_conditions = []
        for col_name in cfg["columns"]:
            col = getattr(model, col_name, None)
            if col is not None:
                keyword_conditions.append(col.ilike(f"%{escaped}%", escape="\\"))

        filters = base_filters
        if keyword_conditions:
            filters = [*base_filters, or_(*keyword_conditions)]
        keyword_stmt = (
            select(model)
            .where(and_(*filters))
            .limit(limit)
        )
        keyword_rows = (await db.execute(keyword_stmt)).scalars().all()

        for row in keyword_rows:
            results.append(_serialise(etype, row, score=1.0, method="keyword"))

        # Vector search (cosine similarity) — runs if embedding available.
        if embedding is not None:
            vec_col = cfg["vector_col"]
            table = model.__tablename__  # model constant, never user input
            vec_filters = base_filters + [text(f"{table}.{vec_col} IS NOT NULL")]

            # PostgreSQL pgvector cosine distance: a <=> b (vector passed as a
            # bound parameter — never interpolated into the SQL string).
            similarity_expr = _vector_similarity(vec_col, embedding)

            vec_stmt = (
                select(model, similarity_expr)
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


def _embedding_literal(embedding: list[float]) -> str:
    """Serialize a float vector as a pgvector array literal (floats only)."""
    return "[" + ",".join(repr(float(v)) for v in embedding) + "]"


def _vector_similarity(vec_col: str, embedding: list[float]) -> TextClause:
    """Cosine-distance expression (`a <=> b`) with the vector bound as a parameter."""
    return text(
        f"{vec_col} <=> CAST(:embedding AS vector)"
    ).bindparams(embedding=_embedding_literal(embedding))


def _serialise(etype: str, row, *, score: float, method: str) -> dict:
    """Convert a model row to a search result dict."""
    data = {
        "id": row.id,
        "type": etype,
        "score": round(score, 3),
        "method": method,
        "vehicle_id": getattr(row, "vehicle_id", None),
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
    elif etype == "issue":
        data.update({
            "title": row.title,
            "body": row.body,
            "tags": list(row.tags or []),
            "status": row.status,
            "author_display_name": row.author_display_name,
        })
    elif etype == "fuel_price":
        station = getattr(row, "station", None)
        data.update({
            "fuel_type": row.fuel_type,
            "price": row.price,
            "station_name": getattr(station, "name", None),
            "station_brand": getattr(station, "brand", None),
        })
    elif etype == "device":
        data.update({
            "name": row.name,
            "vehicle_id": row.vehicle_id,
        })
    elif etype == "market_listing":
        data.update({
            "make": row.make,
            "model": row.model,
            "year": row.year,
            "median_price": row.median_price,
        })
    elif etype == "vehicle":
        data.update({
            "nickname": row.nickname,
            "make": row.make,
            "model": row.model,
            "year": row.year,
            "rego": row.rego,
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

    table = model.__tablename__  # model-defined constant, never user input
    await db.execute(
        text(
            f"UPDATE {table} SET embedding = CAST(:embedding AS vector) WHERE id = :id"
        ),
        {"embedding": _embedding_literal(embedding), "id": entity_id},
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
    if entity_type == "issue":
        return {
            "title": row.title,
            "body": row.body,
            "tags": list(row.tags or []),
        }
    if entity_type == "fuel_price":
        station = getattr(row, "station", None)
        return {
            "fuel_type": row.fuel_type,
            "price": row.price,
            "station_name": getattr(station, "name", ""),
            "station_brand": getattr(station, "brand", ""),
            "station_address": getattr(station, "address", ""),
        }
    if entity_type == "device":
        return {
            "name": row.name,
            "vehicle_id": row.vehicle_id,
        }
    if entity_type == "market_listing":
        return {
            "make": row.make,
            "model": row.model,
            "year": row.year,
            "source": row.source,
        }
    if entity_type == "vehicle":
        return {
            "nickname": row.nickname,
            "make": row.make,
            "model": row.model,
            "year": row.year,
            "rego": row.rego,
            "vin": row.vin,
            "colour": row.colour,
            "body_type": row.body_type,
            "engine": row.engine,
            "transmission": row.transmission,
            "fuel_type": row.fuel_type,
            "powertrain": row.powertrain,
            "vehicle_type": row.vehicle_type,
        }
    return {}
