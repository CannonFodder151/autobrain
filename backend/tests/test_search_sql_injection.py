"""Regression tests for AUT-203 S3: embedding values are bound, never
interpolated into SQL. Fail against the old code (no bound-parameter path)."""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost/test"

from sqlalchemy.dialects import postgresql  # noqa: E402

from app.core.config import settings
from app.services.search import _vector_similarity
from app.services.vector_search import _valid_embedding

_DIM = settings.EMBEDDING_DIMENSION


def _vec() -> list[float]:
    """A correctly-sized embedding (matches EMBEDDING_DIMENSION)."""
    return [0.1] * _DIM


def test_vector_similarity_binds_embedding_not_inlines() -> None:
    expr = _vector_similarity("embedding", _vec())
    sql = str(expr.compile(dialect=postgresql.dialect()))

    assert "DROP" not in sql
    # The vector value must be a bound parameter, never inlined. (The postgres
    # dialect renders :name as %(name)s.)
    assert "0.1" not in sql
    assert f"[{_vec()}]" not in sql
    assert "CAST(" in sql and "AS vector)" in sql
    assert ":embedding" in sql or "%(embedding)s" in sql


def test_valid_embedding_accepts_numbers_only() -> None:
    assert _valid_embedding(_vec()) is not None
    assert _valid_embedding([1] * _DIM) is not None  # ints coerced to float

    # Strings / booleans / garbage from a misbehaving router must be rejected.
    assert _valid_embedding(["0.1); DROP TABLE receipts; --"]) is None
    assert _valid_embedding([0.1, True] + _vec()[2:]) is None
    assert _valid_embedding(["0.2"] + _vec()[1:]) is None
    assert _valid_embedding([]) is None
    assert _valid_embedding("0.1,0.2") is None
    assert _valid_embedding(None) is None


def test_valid_embedding_rejects_wrong_dimension() -> None:
    # A router response with the wrong dimension must be skipped (return None)
    # rather than crash later with a vector(1536) insert 22P02 error.
    assert _valid_embedding(_vec() + [0.5]) is None  # too long
    assert _valid_embedding(_vec()[:-1]) is None  # too short
    assert _valid_embedding([0.1, -0.2, 3.0]) is None  # tiny (old hardcoded 3)
