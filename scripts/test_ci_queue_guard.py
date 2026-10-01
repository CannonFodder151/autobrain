#!/usr/bin/env python3
"""Regression test for the CI Queue Guard supersede/starvation logic (AUT-4949).

The guard is scripts/ci-queue-guard.sh; it reads its two GitHub inputs from files
when the QUEUED_RUNS_FILE / LIVE_BRANCHES_FILE env vars are set, so the decision
logic runs for real here without touching the API.
"""
import os
import re
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci-queue-guard.sh")


def run_guard(rows, live_branches=("main",), env_extra=None):
    """rows: list of (id, created_at, event, branch, name, sha) tuples."""
    env = dict(os.environ)
    env.update(
        {
            "DRY_RUN": "1",
            "PUSH_TTL_MINUTES": "45",
            "PR_TTL_MINUTES": "240",
            "NOW_EPOCH": str(int(FIXED_NOW.timestamp())),
        }
    )
    env.update(env_extra or {})
    with tempfile.TemporaryDirectory() as tmp:
        runs_f, branches_f = os.path.join(tmp, "runs"), os.path.join(tmp, "branches")
        with open(runs_f, "w") as fh:
            fh.write("".join("\t".join(str(c) for c in r) + "\n" for r in rows))
        with open(branches_f, "w") as fh:
            fh.write("".join(b + "\n" for b in live_branches))
        env["QUEUED_RUNS_FILE"] = runs_f
        env["LIVE_BRANCHES_FILE"] = branches_f
        proc = subprocess.run(
            ["bash", GUARD, "autobrain"],
            capture_output=True,
            text=True,
            env=env,
        )
    if proc.returncode != 0:
        raise AssertionError(f"guard failed: {proc.stderr}")
    cancelled = {
        int(m.group(1))
        for m in re.finditer(r"run (\d+): WOULD CANCEL \((.+)\)", proc.stdout)
    }
    return cancelled, proc.stdout


# Fixed clock so age assertions are deterministic.
FIXED_NOW = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)


def ts(minutes_ago):
    return (FIXED_NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestCIQueueGuard(unittest.TestCase):
    def test_keeps_newest_per_workflow_and_ref(self):
        rows = [
            (1, ts(10), "push", "main", "Build hosted images", "aaa"),
            (2, ts(5), "push", "main", "Build hosted images", "bbb"),
        ]
        cancelled, out = run_guard(rows)
        self.assertEqual(cancelled, {1}, out)
        self.assertIn("superseded", out)

    def test_does_not_supersede_across_different_refs(self):
        rows = [
            (1, ts(10), "push", "main", "Build hosted images", "aaa"),
            (2, ts(5), "push", "feat/x", "Build hosted images", "bbb"),
        ]
        cancelled, out = run_guard(rows, live_branches=("main", "feat/x"))
        self.assertEqual(cancelled, set(), out)

    def test_never_touches_in_flight_newest(self):
        # Only one queued run exists and it is the newest — must survive even though
        # a runner may already be executing an older sibling.
        rows = [(9, ts(2), "push", "main", "Build hosted images", "ccc")]
        cancelled, out = run_guard(rows)
        self.assertEqual(cancelled, set(), out)

    def test_cancels_starved_push_run_older_than_ceiling(self):
        # Distinct workflows, so the supersede rule cannot fire and the TTL is the
        # only thing that can cancel run 1.
        rows = [
            (1, ts(300), "push", "main", "Code Review", "aaa"),
            (2, ts(1), "push", "main", "Publish images to Docker Hub", "bbb"),
        ]
        cancelled, out = run_guard(rows)
        self.assertEqual(cancelled, {1}, out)
        self.assertIn("ceiling", out)

    def test_pull_request_not_superseded_but_tolerated_by_pr_ceiling(self):
        rows = [
            (1, ts(100), "pull_request", "feat/x", "Backend smoke", "aaa"),
            (2, ts(1), "pull_request", "feat/x", "Backend smoke", "bbb"),
        ]
        # 100m would breach the 45m push ceiling, but the PR ceiling is 240m and the
        # supersede rule deliberately does not apply to pull_request events, so this
        # run must survive.
        cancelled, out = run_guard(rows, live_branches=("feat/x",))
        self.assertEqual(cancelled, set(), out)
        self.assertIn("under 240m ceiling", out)

    def test_pull_request_cancelled_past_pr_ceiling(self):
        rows = [
            (1, ts(300), "pull_request", "feat/x", "Backend smoke", "aaa"),
            (2, ts(1), "pull_request", "feat/x", "Backend smoke", "bbb"),
        ]
        cancelled, out = run_guard(rows, live_branches=("feat/x",))
        self.assertEqual(cancelled, {1}, out)
        self.assertIn("ceiling", out)

    def test_cancels_run_whose_branch_is_gone(self):
        rows = [
            (1, ts(1), "push", "gone/branch", "Security scan", "aaa"),
            (2, ts(0), "push", "gone/branch", "Security scan", "bbb"),
        ]
        cancelled, out = run_guard(rows, live_branches=("main",))
        self.assertEqual(cancelled == {1}, True, out)
        self.assertIn("head branch gone", out)

    def test_lone_starved_newest_run_is_freed(self):
        # A single queued run has no newer sibling, so the supersede rule cannot
        # help. Only the ceiling can free it.
        rows = [(1, ts(300), "push", "main", "Build hosted images", "aaa")]
        cancelled, out = run_guard(rows)
        self.assertEqual(cancelled, {1}, out)
        self.assertIn("ceiling", out)

    def test_fresh_lone_run_is_kept(self):
        rows = [(1, ts(3), "push", "main", "Build hosted images", "aaa")]
        cancelled, out = run_guard(rows)
        self.assertEqual(cancelled, set(), out)
        self.assertIn("keeping", out)

    def test_skips_scheduled_guard_ticks(self):
        rows = [
            (1, ts(600), "schedule", "main", "CI Queue Guard", "aaa"),
            (2, ts(500), "schedule", "main", "CI Queue Guard", "bbb"),
        ]
        cancelled, out = run_guard(rows)
        self.assertEqual(cancelled, set(), out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
