"""Alembic migration-graph regression guard (AUT-702) + model-metadata smoke (AUT-2277).

Asserts the migration chain has exactly ONE head so ``alembic upgrade head``
works at bootstrap instead of silently falling back to ``create_all``. Catches
head-fork reintroductions (AUT-675's merge, the Issues Blog migration's fork,
this merge re-unifying them).

Also asserts revision IDs are unique (AUT-918/AUT-1009: add_devices reused
revision ``a1b2c3d4e5f6`` already claimed by add_user_max_vehicles, so alembic
refused to load the script tree and every deploy fell back to create_all).

Runs offline — no DB, no app settings — it only walks the versions directory.

The ``test_no_duplicate_table_names`` smoke catches duplicate ORM table
declarations (e.g. two ``FuelPrice`` classes claiming ``fuel_prices`` in
AUT-2277) before pytest collection fails or startup blows up.
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


def test_no_duplicate_table_names() -> None:
    """AUT-2277: no two ORM model classes may claim the same ``__tablename__``.

    Scans the model modules without importing them (so this test does not
    collide with the SQLAlchemy metadata-collision error it is guarding
    against). Catches re-introductions of duplicate ``fuel_prices``
    declarations and similar foot-guns before pytest collection or app boot
    fails.
    """
    import importlib.util
    from pathlib import Path

    models_dir = BACKEND_DIR / "app" / "models"
    assert models_dir.is_dir(), f"models dir missing: {models_dir}"

    seen: dict[str, str] = {}
    dups: list[tuple[str, str, str]] = []
    for py in sorted(models_dir.glob("*.py")):
        if py.name == "__init__.py":
            continue
        spec = importlib.util.spec_from_file_location(
            f"_models_scan_{py.stem}", py
        )
        assert spec and spec.loader, f"failed to load spec for {py}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # noqa: S602 — trusted local file
        for cls_name, cls in vars(module).items():
            if not isinstance(cls, type):
                continue
            tbl = getattr(cls, "__tablename__", None)
            if not tbl or not isinstance(tbl, str):
                continue
            if tbl in seen:
                dups.append((tbl, seen[tbl], f"{py.stem}.{cls_name}"))
            else:
                seen[tbl] = f"{py.stem}.{cls_name}"
    assert not dups, (
        f"Duplicate __tablename__ across model classes: "
        + "; ".join(f"{t} claimed by {a} and {b}" for t, a, b in dups)
    )
