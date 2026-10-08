"""AUT-5268: f7e8d9c0b1a2 must reflect unique constraints via real Inspector APIs.

The migration called ``PGInspector.get_constraints``, which does not exist
anywhere in SQLAlchemy, so every ``alembic upgrade head`` crashed at this
revision, fell back to ``create_all`` and left ``alembic_version`` stuck at
two rows (a3661engineers, aut3447_passkey_credentials) on EP2 Default.

Runs offline on an in-memory SQLite database (no Postgres needed). Reflection
(``get_table_names`` / ``get_unique_constraints``) runs against a REAL
``Inspector`` so any non-existent Inspector method fails the test; the DDL
ops are only recorded because SQLite cannot ALTER constraints.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parent.parent
MIGRATION_PATH = (
    BACKEND_DIR
    / "alembic"
    / "versions"
    / "f7e8d9c0b1a2_unique_passkey_credential_per_user.py"
)
CONSTRAINT = "uq_passkey_credential_user_credential"
CREATE_TABLE_DDL = (
    "CREATE TABLE passkey_credentials "
    "(user_id TEXT NOT NULL, credential_id TEXT NOT NULL)"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("aut5268_f7e8d9c0b1a2", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingOp:
    """Alembic ``op`` stand-in: real bind, DDL recorded instead of executed."""

    def __init__(self, bind):
        self._bind = bind
        self.calls = []

    def get_bind(self):
        return self._bind

    def create_unique_constraint(self, *args, **kwargs):
        self.calls.append(("create_unique_constraint", args, kwargs))

    def drop_constraint(self, *args, **kwargs):
        self.calls.append(("drop_constraint", args, kwargs))


class _InspectorShim:
    """Real Inspector plus PG-style named unique constraints.

    SQLite reflection reports table-level ``UNIQUE (a, b)`` with no name
    and unique indexes under ``get_indexes``, so the "constraint already
    exists" state cannot be produced by DDL alone on SQLite.
    """

    def __init__(self, insp, named_constraints):
        self._insp = insp
        self._named = named_constraints

    def __getattr__(self, name):
        return getattr(self._insp, name)

    def get_unique_constraints(self, table_name, **kwargs):
        found = list(self._insp.get_unique_constraints(table_name, **kwargs))
        if table_name == "passkey_credentials":
            found.extend(self._named)
        return found


def _run_step(engine, *, create_table, named_constraints, step, offline=False):
    """Run one migration step against a real Inspector; return recorded DDL calls."""
    with engine.begin() as conn:
        if create_table:
            conn.execute(sa.text(CREATE_TABLE_DDL))
        module = _load_migration()
        if named_constraints:
            insp = sa.inspect(conn)
            module.sa = SimpleNamespace(
                inspect=lambda bind: _InspectorShim(insp, named_constraints)
            )
        module.op = _RecordingOp(conn)
        module.context = SimpleNamespace(is_offline_mode=lambda: offline)
        getattr(module, step)()
        return module.op.calls


def _named_constraint():
    return [{"name": CONSTRAINT, "column_names": ["user_id", "credential_id"]}]


def test_reflection_uses_existing_inspector_api() -> None:
    """Root-cause pin: the Inspector API this migration needs must exist."""
    insp = sa.inspect(sa.create_engine("sqlite:///:memory:"))
    assert hasattr(insp, "get_unique_constraints")
    assert not hasattr(insp, "get_constraints")


def test_upgrade_creates_constraint_when_absent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    calls = _run_step(engine, create_table=True, named_constraints=[], step="upgrade")
    assert [c[0] for c in calls] == ["create_unique_constraint"]
    assert calls[0][1] == (CONSTRAINT, "passkey_credentials", ["user_id", "credential_id"])


def test_upgrade_is_idempotent_when_constraint_exists() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    calls = _run_step(
        engine, create_table=True, named_constraints=_named_constraint(), step="upgrade"
    )
    assert calls == []


def test_upgrade_is_noop_when_table_absent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    calls = _run_step(engine, create_table=False, named_constraints=[], step="upgrade")
    assert calls == []


def test_downgrade_drops_constraint_when_present() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    calls = _run_step(
        engine, create_table=True, named_constraints=_named_constraint(), step="downgrade"
    )
    assert [c[0] for c in calls] == ["drop_constraint"]
    assert calls[0][1] == (CONSTRAINT, "passkey_credentials")
    assert calls[0][2] == {"type_": "unique"}


def test_downgrade_is_noop_when_constraint_absent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    calls = _run_step(engine, create_table=True, named_constraints=[], step="downgrade")
    assert calls == []


def test_downgrade_is_noop_when_table_absent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    calls = _run_step(engine, create_table=False, named_constraints=[], step="downgrade")
    assert calls == []


def test_offline_mode_is_always_noop() -> None:
    for step in ("upgrade", "downgrade"):
        engine = sa.create_engine("sqlite:///:memory:")
        calls = _run_step(
            engine,
            create_table=True,
            named_constraints=_named_constraint(),
            step=step,
            offline=True,
        )
        assert calls == []
