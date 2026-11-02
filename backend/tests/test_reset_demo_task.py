"""Scheduled reset_demo Celery task (AUT-148).

The task wraps app.db.seed.reset_demo and must fail closed the same way:
it does nothing when DEMO_MODE is off, and it delegates to seed.reset_demo
which skips when DEMO_PASSWORD is unset/whitespace-only.

Run:
    cd backend && python3 -m pytest tests/test_reset_demo_task.py -q
"""

import asyncio

import pytest

from app.core.config import settings
from app.workers import tasks

pytestmark = pytest.mark.asyncio


async def test_reset_demo_task_skips_when_not_demo_mode(monkeypatch) -> None:
    calls: list[bool] = []

    async def fake_reset() -> None:
        calls.append(True)

    monkeypatch.setattr("app.db.seed.reset_demo", fake_reset)
    monkeypatch.setattr(settings, "DEMO_MODE", False)

    captured: list = []

    def fake_run(coro):
        captured.append(coro)
        return None

    monkeypatch.setattr(tasks, "_run", fake_run)

    tasks.reset_demo()

    assert calls == [], "must not reset when DEMO_MODE is off"
    assert len(captured) == 1
    await captured[0]


async def test_reset_demo_task_runs_when_demo_mode(monkeypatch) -> None:
    calls: list[bool] = []

    async def fake_reset() -> None:
        calls.append(True)

    monkeypatch.setattr("app.db.seed.reset_demo", fake_reset)
    monkeypatch.setattr(settings, "DEMO_MODE", True)

    captured: list = []

    def fake_run(coro):
        captured.append(coro)
        return None

    monkeypatch.setattr(tasks, "_run", fake_run)

    tasks.reset_demo()

    assert calls == [], "reset must not run before the coroutine executes"
    assert len(captured) == 1
    await captured[0]
    assert calls == [True], "must run reset_demo when DEMO_MODE is on"