"""stdlib-logger / structlog call-style mismatch guard (AUT-5267).

AUT-5267: ``app/services/backup_offsite.py`` bound a stdlib logger
(``logging.getLogger(...)``) but called it structlog-style —
``logger.error("offsite_push_failed", filename=..., error=...)``.
stdlib forwards the extra kwargs to ``Logger._log()``, which raises
``TypeError: Logger._log() got an unexpected keyword argument
'filename'``. Because that raised *inside the error handler*, every
failed hourly offsite push reported the TypeError instead of the real
cause (a missing ``logbook_entries.vehicle_type`` column), and the
outage stayed invisible for six hours.

Scans ``backend/app`` without importing it: any module that binds a
logger from ``logging.getLogger`` must only call it with the kwargs
stdlib's ``Logger._log`` accepts (``exc_info``/``stack_info``/
``stacklevel``/``extra``) — or with %-style ``args``. Structured
kwargs belong to structlog loggers from ``app.core.logging.get_logger``.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"

# kwargs stdlib Logger._log() accepts (everything else -> TypeError).
STDLIB_LOG_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel", "extra"})
LOG_LEVELS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical"}
)


def _stdlib_logger_names(tree: ast.Module) -> set[str]:
    """Local names bound from logging.getLogger(...)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "getLogger"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "logging"
        ):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _bad_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = _stdlib_logger_names(tree)
    if not offenders:
        return []
    problems: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in offenders
            and node.func.attr in LOG_LEVELS
        ):
            continue
        for kw in node.keywords:
            if kw.arg is None or kw.arg in STDLIB_LOG_KWARGS:
                continue
            problems.append(
                f"{path.relative_to(BACKEND_DIR)}:{node.lineno} "
                f"logger.{node.func.attr}(..., {kw.arg}=...) on a stdlib logger"
            )
    return problems


def test_no_structlog_kwargs_on_stdlib_loggers() -> None:
    problems: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        problems.extend(_bad_calls(path))
    assert not problems, (
        "stdlib loggers must not be called with structlog-style kwargs "
        "(they raise TypeError inside Logger._log and mask the real error). "
        "Use app.core.logging.get_logger for structured logging: "
        + "; ".join(problems)
    )
