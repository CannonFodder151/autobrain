#!/usr/bin/env python3
"""AUT-5755: no pull_request-triggered job may run on a persistent self-hosted runner.

`CannonFodder151/autobrain` is a public repo. A `pull_request` from a fork
executes attacker-controlled code, and the self-hosted fleet runs as a uid
whose $HOME holds /home/administrator/.env and whose groups include docker
and sudo. That is a "pwn request" RCE (GHSA-8x5q-6f9x / GHSA-4r62-v4vq-8hh6).

Two controls close it, and this script enforces the second one so it cannot
rot:

  1. Repo posture: `pull_request_creation_policy: collaborators_only`, so only
     users with write access can open a PR at all.
  2. Workflow posture: every job in a `pull_request`-triggered workflow that
     runs on `self-hosted` (or on a dynamic/matrix selector) carries the
     fork-PR guard, so a fork PR is skipped before it is ever dispatched.

The guard is evaluated by GitHub before a runner is assigned, so a missing
guard means untrusted code reaches the fleet.

Stdlib only. Exits 1 with a per-job report on any violation.
"""

from __future__ import annotations

import pathlib
import re
import sys

WORKFLOWS = pathlib.Path(".github/workflows")

# Canonical fork-PR guard. `github.event_name != 'pull_request'` is first so
# the `||` short-circuits on push/schedule/dispatch, where
# `github.event.pull_request` does not exist.
GUARD = (
    "github.event_name != 'pull_request' || "
    "github.event.pull_request.head.repo.full_name == github.repository"
)

# A job-level `if:` that already excludes the pull_request event entirely is
# equivalent to the guard (e.g. `if: github.event_name != 'pull_request'`).
_EXCLUDES_PR = re.compile(r"github\.event_name\s*!=\s*['\"]pull_request['\"]")

_JOB_HEADER = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_TOP_KEY = re.compile(r"^([A-Za-z0-9_.-]+):")
_RUNS_ON = re.compile(r"^    runs-on:\s*(.+?)\s*$")
_JOB_IF = re.compile(r"^    if:\s*(.+?)\s*$")


def _triggers_pull_request(lines):
    """True when the workflow's `on:` block declares a pull_request trigger."""
    on_index = None
    for index, line in enumerate(lines):
        if line.startswith("on:"):
            on_index = index
            break
    if on_index is None:
        return False
    # Flow style: `on: [push, pull_request]`.
    if re.match(r"^on:\s*\[", lines[on_index]):
        return "pull_request" in lines[on_index]
    # Block style: trigger keys sit at two-space indent, up to the next
    # top-level key.
    for line in lines[on_index + 1:]:
        if _TOP_KEY.match(line):
            break
        if re.match(r"^  pull_request:", line):
            return True
    return False


def _jobs(lines):
    """Split the `jobs:` block into one record per job, with line numbers."""
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("jobs:"))
    except StopIteration:
        return []
    jobs = []
    current = None
    for index in range(start + 1, len(lines)):
        line = lines[index]
        header = _JOB_HEADER.match(line)
        if header:
            if current is not None:
                jobs.append(current)
            current = {"id": header.group(1), "start": index, "runs_on": "",
                       "runs_on_line": None, "if": "", "if_line": None}
            continue
        if current is None:
            continue
        runs_on = _RUNS_ON.match(line)
        if runs_on and current["runs_on_line"] is None:
            current["runs_on"] = runs_on.group(1)
            current["runs_on_line"] = index
        job_if = _JOB_IF.match(line)
        if job_if and current["if_line"] is None:
            current["if"] = job_if.group(1)
            current["if_line"] = index
    if current is not None:
        jobs.append(current)
    return jobs


def violations(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not _triggers_pull_request(lines):
        return []
    found = []
    for job in _jobs(lines):
        runs_on = job["runs_on"]
        # A dynamic selector (matrix.runs_on) can resolve to self-hosted, so
        # treat it as self-hosted: fail closed.
        if "self-hosted" not in runs_on and "${{" not in runs_on:
            continue
        job_if = job["if"]
        if GUARD in job_if or _EXCLUDES_PR.search(job_if):
            continue
        found.append(
            f"{path}:{job['start'] + 1}: job `{job['id']}` runs on "
            f"`{runs_on}` for pull_request without the fork-PR guard")
    return found


def main():
    if not WORKFLOWS.is_dir():
        print(f"::error::missing {WORKFLOWS} directory", file=sys.stderr)
        return 1
    paths = sorted(WORKFLOWS.glob("*.yml"))
    bad = []
    for path in paths:
        bad.extend(violations(path))
    if bad:
        print("::error::pull_request-triggered self-hosted jobs missing the "
              "AUT-5755 fork-PR guard:")
        for line in bad:
            print(f"  {line}")
        print(f"\nAdd to each job:  if: {GUARD}")
        return 1
    print(f"OK: every pull_request-triggered self-hosted job carries the "
          f"AUT-5755 fork-PR guard ({len(paths)} workflows scanned).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
