"""AUT-5137: a failed ``alembic upgrade`` must abort startup, not fall open.

``bootstrap()`` used to catch every alembic failure and degrade to
``Base.metadata.create_all``. ``create_all`` never alters an existing table,
so for any migration that only adds a column it silently did nothing while
boot proceeded — a deploy that reports success with the wrong schema. Two
real defects were swallowed this way (AUT-5122's varchar truncation, the
AUT-4925 head fork in AUT-5114).

The fallback now survives only for a genuinely fresh database (no tables at
all). Covered below:

* failing migration + non-empty database -> startup aborts, with the
  structured abort log line and the ops alert fired first;
* failing migration + empty database -> ``create_all`` still runs and boot
  continues (the pre-first-migration bring-up case);
* database state that cannot be inspected -> fail closed.

The tests drive the database seam (``app.db.session.engine``) and the alembic
CLI seam (``app.db.bootstrap.subprocess.run``) rather than any new helper, so
they run unchanged against the pre-fix bootstrap and fail there.
"""

import pytest
from structlog.testing import capture_logs

from app.core.config import settings
from app.db import bootstrap as bs

_ALEMBIC_STDERR = (
    "psycopg.errors.StringDataRightTruncation: value too long for type "
    "character varying(32)"
)


def _alembic_result(returncode: int, stderr: str = ""):
    return type("R", (), {"returncode": returncode, "stdout": "", "stderr": stderr})()


def _fail_alembic(monkeypatch) -> list[str]:
    """Make every ``alembic upgrade`` attempt fail; return the targets tried."""
    targets: list[str] = []

    def _run(cmd, **kwargs):
        targets.append(cmd[-1])
        return _alembic_result(1, _ALEMBIC_STDERR)

    monkeypatch.setattr(bs.subprocess, "run", _run)
    return targets


class _FakeConn:
    def __init__(self, value) -> None:
        self._value = value

    async def scalar(self, *args, **kwargs):
        return self._value

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeEngine:
    """Answers ``information_schema`` probes with a fixed table count."""

    def __init__(self, table_count: int) -> None:
        self.table_count = table_count
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        return _FakeConn(self.table_count)


async def _noop() -> None:
    return None


def _stub_seeds(monkeypatch, seeded: list[str] | None = None) -> None:
    if seeded is None:
        monkeypatch.setattr(bs, "_seed_admin", _noop)
        monkeypatch.setattr(bs, "_seed_demo", _noop)
    else:
        async def _record_admin() -> None:
            seeded.append("admin")

        async def _record_demo() -> None:
            seeded.append("demo")

        monkeypatch.setattr(bs, "_seed_admin", _record_admin)
        monkeypatch.setattr(bs, "_seed_demo", _record_demo)


def _patch_engine(monkeypatch, table_count: int) -> _FakeEngine:
    import app.db.session as session

    engine = _FakeEngine(table_count)
    monkeypatch.setattr(session, "engine", engine)
    return engine


def _patch_init_db(monkeypatch) -> list[bool]:
    """Record create_all calls — the fail-open path."""
    import app.db.session as session

    created: list[bool] = []

    async def _fake_init_db() -> None:
        created.append(True)

    monkeypatch.setattr(session, "init_db", _fake_init_db)
    return created


def test_failed_migration_aborts_startup(monkeypatch) -> None:
    """Failing alembic against a non-empty DB aborts boot instead of falling open.

    Before the fix this ran ``create_all`` (a no-op for an existing table) and
    returned normally, so the deploy looked successful with the schema unchanged.
    """
    targets = _fail_alembic(monkeypatch)
    _stub_seeds(monkeypatch)
    _patch_engine(monkeypatch, table_count=42)  # a real, migrated database
    created = _patch_init_db(monkeypatch)

    alerts: list[dict] = []
    # raising=False: the alert hook is part of the fix, not the seam
    # under test. On the pre-fix bootstrap there is no hook to patch,
    # and the test still has to fail on the missing abort itself.
    monkeypatch.setattr(bs, "_alert", alerts.append, raising=False)
    monkeypatch.setattr(settings, "BOOT_ALERT_WEBHOOK_URL", "http://ops.test/hook")

    with capture_logs() as logs:
        with pytest.raises(RuntimeError) as exc:
            bs.bootstrap()

    assert created == [], "create_all must not run against a non-empty database"
    # Both upgrade targets must have been tried before giving up.
    assert targets == ["head", "heads"]

    # The real cause has to survive into the fatal error, or the operator
    # gets "refusing to fall back" and nothing else.
    assert "StringDataRightTruncation" in str(exc.value)

    # Fail loudly, then abort: this line is all a crash-looping container
    # leaves behind.
    abort = [entry for entry in logs if entry.get("event") == "migration_failed_startup_aborted"]
    assert len(abort) == 1, f"expected one structured abort line, got {logs}"
    assert abort[0]["log_level"] == "error"
    assert "StringDataRightTruncation" in abort[0]["error"]
    assert abort[0]["environment"] == settings.ENVIRONMENT

    # And alert before aborting, so a human hears about it without polling logs.
    assert [a["event"] for a in alerts] == ["migration_failed_startup_aborted"]
    assert "StringDataRightTruncation" in alerts[0]["error"]


def test_failed_migration_on_fresh_database_still_creates_schema(monkeypatch) -> None:
    """An empty database keeps the create_all fallback — the bring-up case.

    Scoped to a database with no tables at all, which is what a genuinely
    new deployment looks like before the first migration is authored.
    """
    _fail_alembic(monkeypatch)
    seeded: list[str] = []
    _stub_seeds(monkeypatch, seeded)
    _patch_engine(monkeypatch, table_count=0)  # fresh, un-stamped
    created = _patch_init_db(monkeypatch)

    with capture_logs() as logs:
        bs.bootstrap()

    assert created == [True], "fresh database must still get create_all"
    assert seeded == ["admin", "demo"], "seeding must still run after the fallback"
    # The fallback is now labelled as fresh-only, and never as an abort.
    assert [e["event"] for e in logs if "create_all" in e.get("event", "")]
    assert not [e for e in logs if e.get("event") == "migration_failed_startup_aborted"]


def test_unverifiable_database_state_fails_closed(monkeypatch) -> None:
    """If the database cannot be inspected, boot aborts rather than guessing.

    An unreachable database means we cannot tell fresh from drifted, and
    ``create_all`` against unknown state is the silent-drift path itself.
    """
    _fail_alembic(monkeypatch)
    _stub_seeds(monkeypatch)

    import app.db.session as session

    def _unreachable():
        raise OSError("could not connect to server")

    monkeypatch.setattr(session, "engine", type("E", (), {"connect": staticmethod(_unreachable)})())
    monkeypatch.setattr(bs, "_alert", lambda payload: None, raising=False)

    with pytest.raises(RuntimeError) as exc:
        bs.bootstrap()

    assert "could not connect to server" in str(exc.value)


def test_successful_migration_never_probes_the_database(monkeypatch) -> None:
    """A clean ``alembic upgrade head`` skips both the probe and create_all."""
    monkeypatch.setattr(bs.subprocess, "run", lambda cmd, **kw: _alembic_result(0))
    _stub_seeds(monkeypatch)
    engine = _patch_engine(monkeypatch, table_count=42)
    _patch_init_db(monkeypatch)

    bs.bootstrap()

    assert engine.connect_calls == 0, "schema must not be probed after a clean upgrade"