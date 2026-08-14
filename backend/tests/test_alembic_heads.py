"""Alembic migration-graph regression guard (AUT-702).

Asserts the migration chain has exactly ONE head so `alembic upgrade head`
works at bootstrap instead of silently falling back to `create_all`. Catches
head-fork reintroductions (AUT-675's merge, the Issues Blog migration's fork,
this merge re-unifying them).

Runs offline — no DB, no app settings — it only walks the versions directory.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _heads() -> list[str]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return sorted(ScriptDirectory.from_config(cfg).get_heads())


def test_alembic_single_head() -> None:
    heads = _heads()
    assert len(heads) == 1, f"expected a single alembic head, got {len(heads)}: {heads}"
