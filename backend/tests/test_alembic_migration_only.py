"""AUT-5088: prove `alembic upgrade head` is the real schema path.

Hosted booted straight into ``python -m app.db.bootstrap``, whose ``create_all``
fallback swallowed every migration failure, so migration-only changes (new
index, constraint, column rename, data backfill) were dead code in production.
Static compose guards catch a deleted ``alembic upgrade head``; this module
catches the other half — a chain that no longer applies cleanly from zero, or a
data-only revision that stopped doing anything.

Both cases build their own throwaway database from ``ALEMBIC_TEST_ADMIN_URL``
(``postgresql://user:pass@host:5432/postgres``) and run the real ``alembic``
CLI against it, so nothing here needs the dev or hosted stack. Skipped when
that variable is unset; the ``alembic-migrations`` CI job sets it against a
``pgvector/pgvector:pg17`` service, matching the hosted postgres image.
"""
import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("ALEMBIC_TEST_ADMIN_URL", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="ALEMBIC_TEST_ADMIN_URL not set (no throwaway postgres)"
)

def _head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()

def _alembic(dsn: str, *args: str) -> None:
    """Run the real alembic CLI against `dsn`."""
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        # The app only has asyncpg installed, so the URL needs the async driver.
        env={
            **os.environ,
            "DATABASE_URL": (
                dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
                if dsn.startswith("postgresql://")
                else dsn
            ),
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"alembic {' '.join(args)} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    )

async def _sql(dsn: str, query: str, *args):
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetchval(query, *args)
    finally:
        await conn.close()

async def _exec(dsn: str, query: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(query)
    finally:
        await conn.close()

@pytest.fixture()
def fresh_db():
    """Create an empty database, yield its DSN, drop it afterwards."""
    name = f"autotest_{uuid.uuid4().hex[:12]}"
    dsn = ADMIN_URL.rsplit("/", 1)[0] + "/" + name

    async def create() -> None:
        await _exec(ADMIN_URL, f'CREATE DATABASE "{name}"')

    asyncio.run(create())
    try:
        yield dsn
    finally:
        asyncio.run(_exec(ADMIN_URL, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))

def test_fresh_database_reaches_head(fresh_db):
    """An empty database must reach head with the hosted-relevant tables."""
    _alembic(fresh_db, "upgrade", "head")
    assert asyncio.run(_sql(fresh_db, "select version_num from alembic_version")) == _head()
    for table in ("fuel_price_snapshots", "passkey_credentials", "engineers"):
        assert asyncio.run(
            _sql(fresh_db, "select to_regclass($1) is not null", f"public.{table}")
        ), f"{table} missing after upgrade head"
    assert asyncio.run(
        _sql(
            fresh_db,
            "select atttypid = 'vector'::regtype from pg_attribute "
            "where attrelid = 'receipts'::regclass and attname = 'embedding'",
        )
    ), "receipts.embedding is not a pgvector column after upgrade head"

def test_migration_only_backfill_applies(fresh_db):
    """b4c5d6e7f8a9 folds legacy oil service records into 'scheduled'.

    That is a pure data rewrite — no schema change — so ``create_all`` can
    never perform it. It only happens if the migration chain actually runs.
    """
    _alembic(fresh_db, "upgrade", "m3rge03")
    asyncio.run(
        _exec(
            fresh_db,
            "INSERT INTO users (id, email, display_name, hashed_password) "
            "VALUES ('u1', 'u1@example.com', 'U One', 'x');"
            "INSERT INTO vehicles (id, user_id, nickname) "
            "VALUES ('v1', 'u1', 'Car');"
            "INSERT INTO service_records (id, vehicle_id, service_date, odometer_km, service_type) "
            "VALUES ('s1', 'v1', current_date, 1000, 'oil');",
        )
    )
    _alembic(fresh_db, "upgrade", "head")
    assert asyncio.run(
        _sql(fresh_db, "select service_type from service_records where id = 's1'")
    ) == "scheduled"