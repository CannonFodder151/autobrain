#!/usr/bin/env python3
"""Fail if any workflow targets a GitHub-hosted runner (AUT-5654).

Why this guard exists: on 2026-10-05 the account's hosted-runner spending
limit ran out, and every GitHub-hosted job in this private repo started
failing in 3-6 seconds with zero steps executed and the check-run
annotation "The job was not started because recent account payments have
failed or your spending limit needs to be increased". The failure is
invisible in the workflow log because there is no log — the only evidence
is the annotation, and only if you go looking for it.

The jobs that needed them were moved to the self-hosted runners, which
fixed CI. What does not exist is anything that stops the next workflow
being added with `runs-on: ubuntu-latest` and silently re-breaking every
push. This script is that stop.

Scope: the AutoBrain fleet. AUT-5654 converted every GitHub-hosted job
in this repo as well, at the reporter's explicit request ("convert all
GitHub runners to self hosted to resolve outage"), so no workflow here may
name a hosted image again. The trade-off is that this repo now leans on a
two-runner x64 fleet (gh-runner-autobrain, gh-runner-autobrain-2); capacity
and vm2 disk headroom are tracked as separate follow-up work.

Run: python3 scripts/check_hosted_runners.py [workflow_dir]
Exit: 0 clean, 1 if any workflow targets a hosted runner.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# A GitHub-hosted label. Matched as a prefix on the architecture family so a
# pinned image (ubuntu-24.04, macos-15) is caught as well as the rolling tag.
# `self-hosted` never matches: the runner is a label, not a hosted image.
HOSTED = re.compile(r"\b(?:ubuntu|macos|windows)-", re.IGNORECASE)

# Only a `runs-on:` line is a dependency. Naming a hosted image in a comment,
# or in a note explaining why a job used to be hosted, must not fail the build.
RUNS_ON = re.compile(r"^\s*runs-on\s*:")


def offending_lines(text: str) -> list[str]:
    """Return the `runs-on:` lines in `text` that name a GitHub-hosted runner."""
    found = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0] if not raw.lstrip().startswith("#") else ""
        if not RUNS_ON.match(line):
            continue
        if HOSTED.search(line):
            found.append(raw.strip())
    return found


def check(workflow_dir: Path) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    paths = sorted(
        p for p in workflow_dir.iterdir() if p.suffix in (".yml", ".yaml")
    ) if workflow_dir.is_dir() else []
    for path in paths:
        for line in offending_lines(path.read_text(encoding="utf-8")):
            problems.append((path.name, line))
    return problems


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    wf_dir = Path(argv[1]) if len(argv) > 1 else root / ".github" / "workflows"
    if not wf_dir.is_dir():
        print(f"::error::no workflow directory at {wf_dir}", file=sys.stderr)
        return 1

    problems = check(wf_dir)
    for name, line in problems:
        print(
            f"::error::{name} targets a GitHub-hosted runner: {line} "
            "(AUT-5654: hosted runners do not start on this account — "
            "use a self-hosted label)",
            file=sys.stderr,
        )
    if problems:
        print(
            f"AUT-5654: {len(problems)} GitHub-hosted runner reference(s). "
            "GitHub-hosted jobs fail in ~5s with no log, so this only ever "
            "shows up as a red X with no explanation.",
            file=sys.stderr,
        )
        return 1
    print("OK: every job targets a self-hosted runner.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))