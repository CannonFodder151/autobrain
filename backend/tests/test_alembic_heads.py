"""Alembic migration-graph regression guard (AUT-702).

Asserts the migration chain has exactly ONE head so `alembic upgrade head`
works at bootstrap instead of silently falling back to `create_all`. Catches
head-fork reintroductions (AUT-675's merge, the Issues Blog migration's fork,
this merge re-unifying them).

Also asserts revision IDs are unique (AUT-918/AUT-1009: add_devices reused
revision `a1b2c3d4e5f6` already claimed by add_user_max_vehicles, so alembic
refused to load the script tree and every deploy fell back to create_all).

Runs offline — no DB, no app settings — it only walks the versions directory.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_alembic_single_head() -> None:
    heads = sorted(_script_dir().get_heads())
    assert len(heads) == 1, f"expected a single alembic head, got {len(heads)}: {heads}"


def test_alembic_revision_ids_unique() -> None:
    seen: dict[str, list[str]] = {}
    for rev in _script_dir().walk_revisions():
        seen.setdefault(rev.revision, []).append(Path(rev.path).name)
    dups = {rev: files for rev, files in seen.items() if len(files) > 1}
    assert not dups, f"duplicate alembic revision ids: {dups}"
