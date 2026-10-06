#!/usr/bin/env python3
"""AUT-5755: regression tests for check-pr-runner-posture.py.

1. The real .github/workflows tree passes — the guard script must not rot into
   a false FAIL the way the structural guards did on main before AUT-4678.
2. An unguarded pull_request job on a self-hosted runner IS reported, so the
   check cannot be defeated by deleting the guard from a workflow.
3. A push-only workflow on self-hosted is NOT reported: the self-hosted fleet
   stays legitimate for trusted main-branch work.
"""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check-pr-runner-posture.py")

spec = importlib.util.spec_from_file_location("check_pr_runner_posture", SCRIPT)
posture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(posture)

UNGUARDED = """\
name: probe
on:
  pull_request:
jobs:
  bad:
    runs-on: [self-hosted, linux, x64]
    steps:
      - run: echo hi
"""

GUARDED = """\
name: probe
on:
  pull_request:
jobs:
  good:
    if: %s
    runs-on: [self-hosted, linux, x64]
    steps:
      - run: echo hi
""" % posture.GUARD

PUSH_ONLY = """\
name: probe
on:
  push:
    branches: [main]
jobs:
  publish:
    runs-on: [self-hosted, linux, x64, vm2]
    steps:
      - run: echo hi
"""


def _scan(body, tmpdir):
    workflows = os.path.join(tmpdir, ".github", "workflows")
    os.makedirs(workflows, exist_ok=True)
    path = os.path.join(workflows, "probe.yml")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    return posture.violations(pathlib.Path(path))


class TestRealTreePasses(unittest.TestCase):
    def test_script_exits_zero_on_repo_workflows(self):
        r = subprocess.run(
            [sys.executable, SCRIPT], cwd=REPO, capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        self.assertIn("AUT-5755 fork-PR guard", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


class TestDetection(unittest.TestCase):
    def test_unguarded_self_hosted_pr_job_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            found = _scan(UNGUARDED, tmpdir)
        self.assertEqual(len(found), 1, found)
        self.assertIn("`bad`", found[0])

    def test_guarded_self_hosted_pr_job_is_clean(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(_scan(GUARDED, tmpdir), [])

    def test_push_only_workflow_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(_scan(PUSH_ONLY, tmpdir), [])

    def test_dynamic_runs_on_fails_closed(self):
        body = UNGUARDED.replace(
            "runs-on: [self-hosted, linux, x64]",
            "runs-on: ${{ matrix.runs_on }}",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(len(_scan(body, tmpdir)), 1)


if __name__ == "__main__":
    unittest.main()
