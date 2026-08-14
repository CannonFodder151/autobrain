"""Alembic migration chain must stay linear (single head).

Regression for AUT-695: two heads (u1v2w3x4y5z6 issue-blog, q1r2s3t4u5v6
photo-position) forked at p6q7r8s9t0u1, breaking `alembic upgrade head` on
boot so bootstrap fell back to create_all and later migration columns were
never applied. The m3rge02 merge re-unifies the chain; this test fails on any
future fork before it reaches a database.
Run: cd backend && python3 -m pytest tests/test_alembic_chain.py -q
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script() -> ScriptDirectory:
    backend = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_single_alembic_head() -> None:
    assert _script().get_heads() == ["m3rge02"]


def test_merge_covers_both_fork_branches() -> None:
    script = _script()
    reached = {rev.revision for rev in script.walk_revisions("base", "m3rge02")}
    assert "u1v2w3x4y5z6" in reached
    assert "q1r2s3t4u5v6" in reached
