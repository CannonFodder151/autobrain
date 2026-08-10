"""Regression tests for AUT-203 S3: embedding values are bound, never
interpolated into SQL. Fail against the old code (no bound-parameter path)."""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost/test"

from sqlalchemy.dialects import postgresql  # noqa: E402

from app.services.search import _vector_similarity
from app.services.vector_search import _valid_embedding


def test_vector_similarity_binds_embedding_not_inlines() -> None:
    expr = _vector_similarity("embedding", [0.1, -0.2, 0.3])
    sql = str(expr.compile(dialect=postgresql.dialect()))

    assert "DROP" not in sql
    # The vector value must be a bound parameter, never inlined. (The postgres
    # dialect renders :name as %(name)s.)
    assert "0.1" not in sql
    assert "[0.1,-0.2,0.3]" not in sql
    assert "CAST(" in sql and "AS vector)" in sql
    assert ":embedding" in sql or "%(embedding)s" in sql


def test_valid_embedding_accepts_numbers_only() -> None:
    assert _valid_embedding([0.1, -0.2, 3.0]) is not None
    assert _valid_embedding([1, 2, 3]) is not None  # ints coerced to float

    # Strings / booleans / garbage from a misbehaving router must be rejected.
    assert _valid_embedding(["0.1); DROP TABLE receipts; --"]) is None
    assert _valid_embedding([0.1, True]) is None
    assert _valid_embedding([0.1, "0.2"]) is None
    assert _valid_embedding([]) is None
    assert _valid_embedding("0.1,0.2") is None
    assert _valid_embedding(None) is None
