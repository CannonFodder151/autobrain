"""ORM metadata regression guard (AUT-2277).

pytest collection crashed with::

    sqlalchemy.exc.InvalidRequestError: Table 'fuel_prices' is already
    defined for this MetaData instance.

because two ORM classes (``fuel_station.FuelPrice`` and ``fuel_price.FuelPrice``)
shared the same ``__tablename__`` but declared different column sets. SQLAlchemy
refused the second registration. The duplicate was masked at runtime because
the table already existed, but the moment any code path triggered metadata
reflection (Alembic env, ``Base.metadata.create_all``, ``pytest --collect-only``
with eager imports) the suite blew up.

This test imports every model and asserts each ``__tablename__`` is unique. If
anyone reintroduces a duplicate table claim, the test fails fast with a clear
list of the offenders.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("SECRET_KEY", "test")
os.environ.setdefault("MINIO_ACCESS_KEY", "k")
os.environ.setdefault("MINIO_SECRET_KEY", "s")
os.environ.setdefault("POSTGRES_USER", "u")
os.environ.setdefault("POSTGRES_PASSWORD", "p")
os.environ.setdefault("POSTGRES_DB", "db")
os.environ.setdefault("MARKET_DATA_URL", "")
os.environ.setdefault("MARKET_DATA_API_KEY", "")
os.environ.setdefault("ENVIRONMENT", "development")

import app.models  # noqa: E402,F401  (registers every ORM class on Base.metadata)
from app.db.session import Base  # noqa: E402

# Class -> tablename. Sorting makes the failure message deterministic.
_tables: dict[str, list[str]] = {}
for cls in Base.registry.mappers:  # type: ignore[attr-defined]
    cls_obj = cls.class_
    table = getattr(cls_obj, "__tablename__", None)
    if not table:
        continue
    _tables.setdefault(table, []).append(f"{cls_obj.__module__}.{cls_obj.__name__}")


def test_no_duplicate_orm_tablename() -> None:
    duplicates = {t: names for t, names in _tables.items() if len(names) > 1}
    assert not duplicates, (
        "ORM classes share a __tablename__ (AUT-2277): "
        + ", ".join(f"{t} -> {names}" for t, names in sorted(duplicates.items()))
    )
