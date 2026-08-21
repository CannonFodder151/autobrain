"""Embed-on-create smoke tests (AUT-1242-C4).

Verifies the invariants that make embed-on-create work for every entity type:

1. Every entity type produces non-empty searchable text for embedding.
2. `_valid_embedding` guards the dimension correctly on every embed path.

Plus one integration test (skipped unless compose Postgres is reachable)
that creates a row for each of the five entity types, runs the same storage
task `queue_embedding` dispatches (`embed_entity` -> `backfill_entity_embedding`),
and asserts a non-NULL embedding lands in the DB column.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import datetime  # noqa: E402
import uuid  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.diagnostic import Diagnostic  # noqa: E402
from app.models.mod import Modification  # noqa: E402
from app.models.receipt import Receipt  # noqa: E402
from app.models.service import ServiceRecord  # noqa: E402
from app.social.models import SocialIssuePost  # noqa: E402
from app.services.search import backfill_entity_embedding  # noqa: E402
from app.services.vector_search import _valid_embedding, _to_text  # noqa: E402

_EMBED_DIM = settings.EMBEDDING_DIMENSION

# ---------------------------------------------------------------------------
# 1. _to_text — every type must produce non-empty searchable text
# ---------------------------------------------------------------------------

_SAMPLE_DATA: dict[str, dict] = {
    "diagnostic": {
        "symptoms": "Engine knocking on cold start",
        "summary": "Worn bearings detected",
        "severity": "high",
    },
    "service": {
        "description": "Oil change and filter",
        "service_type": "scheduled",
        "notes": "Mobil 1 5W-30",
        "workshop": "Mechanica",
    },
    "modification": {
        "name": "K&N cold air intake",
        "category": "performance",
        "brand": "K&N",
    },
    "receipt": {
        "vendor": "Supercheap Auto",
        "original_name": "receipt_2026-01-01.jpg",
    },
    "issue": {
        "title": "Front brake squeal",
        "body": "High-pitched squeal at low speed braking",
        "tags": ["brakes", "noise"],
    },
}


@pytest.mark.parametrize("entity_type", list(_SAMPLE_DATA.keys()))
def test_to_text_non_empty(entity_type: str) -> None:
    """Each entity type produces searchable text, so embeddings are generatable."""
    result = _to_text(entity_type, _SAMPLE_DATA[entity_type])
    assert result.strip(), f"_to_text({entity_type}) returned empty string"


# ---------------------------------------------------------------------------
# 2. _valid_embedding — dimension + type guard
# ---------------------------------------------------------------------------

class TestValidEmbedding:
    def test_valid_vector(self) -> None:
        vec = [0.1] * _EMBED_DIM
        assert _valid_embedding(vec) == vec

    def test_wrong_dimension_returns_none(self) -> None:
        assert _valid_embedding([0.1] * (_EMBED_DIM - 1)) is None
        assert _valid_embedding([0.1] * (_EMBED_DIM + 1)) is None

    def test_empty_list_returns_none(self) -> None:
        assert _valid_embedding([]) is None

    def test_non_numeric_returns_none(self) -> None:
        assert _valid_embedding(["a"] * _EMBED_DIM) is None

    def test_bool_returns_none(self) -> None:
        assert _valid_embedding([True] * _EMBED_DIM) is None

    def test_mixed_types_returns_none(self) -> None:
        assert _valid_embedding([0.1] * (_EMBED_DIM - 1) + ["x"]) is None

    def test_not_a_list_returns_none(self) -> None:
        assert _valid_embedding("not a list") is None
        assert _valid_embedding(None) is None


# ---------------------------------------------------------------------------
# 3. End-to-end: every entity type lands a non-NULL embedding on create
#    (integration — requires compose Postgres with alembic migrations applied)
# ---------------------------------------------------------------------------

def _pg_reachable() -> bool:
    try:
        import asyncio

        import asyncpg

        async def _ping() -> bool:
            try:
                conn = await asyncpg.connect(
                    dsn=os.environ["DATABASE_URL"].replace("+asyncpg", "")
                )
                await conn.execute("SELECT 1")
                await conn.close()
                return True
            except Exception:
                return False

        return asyncio.run(_ping())
    except Exception:
        return False


_PG_REACHABLE = _pg_reachable()


FAKE_VEC = [0.1] * _EMBED_DIM

_TABLE_BY_TYPE = {
    "diagnostic": "diagnostics",
    "service": "service_records",
    "modification": "modifications",
    "receipt": "receipts",
    "issue": "social_issue_posts",
}


def _make_rows(vehicle_id: str) -> list[tuple[str, object]]:
    return [
        ("diagnostic", Diagnostic(vehicle_id=vehicle_id, symptoms="engine knock")),
        (
            "service",
            ServiceRecord(
                vehicle_id=vehicle_id,
                service_date=datetime.date(2026, 1, 10),
                odometer_km=1000,
                description="oil change",
                status="completed",
            ),
        ),
        ("modification", Modification(vehicle_id=vehicle_id, name="cold air intake")),
        (
            "receipt",
            Receipt(vehicle_id=vehicle_id, file_key="k.jpg", original_name="r.jpg"),
        ),
        (
            "issue",
            SocialIssuePost(
                author_display_name="Tester",
                title="brake squeal",
                body="rear brakes squeal",
                status_hidden=False,
            ),
        ),
    ]


async def _fake_generate(entity_type: str, data: dict) -> list[float]:  # noqa: ARG001
    return FAKE_VEC


@pytest.mark.skipif(not _PG_REACHABLE, reason="requires compose Postgres")
@pytest.mark.asyncio
async def test_embed_on_create_all_types() -> None:
    """All five entity types get a non-NULL embedding via the queue task path."""
    created: list[tuple[str, str]] = []

    async with SessionLocal() as db:
        vehicle_id = str(uuid.uuid4())
        await db.execute(
            text("INSERT INTO vehicles (id, user_id, nickname) VALUES (:id, :uid, :n)"),
            {"id": vehicle_id, "uid": None, "n": "smoke"},
        )
        await db.commit()

        for etype, obj in _make_rows(vehicle_id):
            db.add(obj)
            await db.commit()
            await db.refresh(obj)
            created.append((etype, str(obj.id)))

        # Patch the name bound in search.py (where backfill_entity_embedding
        # lives) so storage runs against a deterministic in-range vector.
        with patch("app.services.search.generate_embedding", new=_fake_generate):
            for etype, entity_id in created:
                ok = await backfill_entity_embedding(db, etype, entity_id)
                assert ok, f"backfill_entity_embedding returned False for {etype}"

        for etype, entity_id in created:
            result = await db.execute(
                text(
                    f"SELECT embedding IS NOT NULL FROM {_TABLE_BY_TYPE[etype]} "
                    "WHERE id = :id"
                ),
                {"id": entity_id},
            )
            assert result.scalar(), f"embedding is NULL after create for {etype}"

        # Cleanup (reverse FK order).
        for etype, entity_id in reversed(created):
            await db.execute(
                text(f"DELETE FROM {_TABLE_BY_TYPE[etype]} WHERE id = :id"),
                {"id": entity_id},
            )
        await db.execute(text("DELETE FROM vehicles WHERE id = :id"), {"id": vehicle_id})
        await db.commit()