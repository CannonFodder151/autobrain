#!/usr/bin/env python3
"""Self-check for scripts/check_hosted_runners.py (AUT-5654).

Proves the two behaviours the guard relies on:
  1. a `runs-on:` line naming a hosted image (ubuntu-latest,
     macos-15, ubuntu-24.04) is reported, and
  2. a hosted image named only in a comment — the "why this used
     to be hosted" note every converted workflow now carries —
     is NOT a violation, and `self-hosted` is never one.

Run: python3 scripts/test_check_hosted_runners.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_hosted_runners as chr  # noqa: E402


class HostedRunnerGuardTest(unittest.TestCase):
    def _write(self, text: str) -> Path:
        d = Path(tempfile.mkdtemp()) / ".github" / "workflows"
        d.mkdir(parents=True)
        (d / "wf.yml").write_text(text, encoding="utf-8")
        return d

    def test_reports_hosted_labels(self):
        d = self._write("jobs:\n  a:\n    runs-on: ubuntu-latest\n")
        self.assertEqual(chr.check(d), [("wf.yml", "runs-on: ubuntu-latest")])

    def test_reports_pinned_hosted_images(self):
        d = self._write("jobs:\n  a:\n    runs-on: ubuntu-24.04\n")
        self.assertEqual(
            chr.check(d), [("wf.yml", "runs-on: ubuntu-24.04")]
        )

    def test_reports_macos_and_windows(self):
        text = "jobs:\n  a:\n    runs-on: macos-latest\n  b:\n    runs-on: windows-latest\n"
        self.assertEqual(len(chr.check(self._write(text))), 2)

    def test_self_hosted_is_not_a_violation(self):
        d = self._write("jobs:\n  a:\n    runs-on: [self-hosted, Linux, X64]\n")
        self.assertEqual(chr.check(d), [])

    def test_comment_mentions_are_ignored(self):
        text = (
            "# AUT-3718: use GitHub-hosted runners (ubuntu-latest) instead of\n"
            "# the self-hosted vm2 runner.\n"
            "jobs:\n  a:\n    runs-on: [self-hosted, Linux, X64]\n"
        )
        self.assertEqual(chr.check(self._write(text)), [])

    def test_trailing_comment_does_not_mask_a_hosted_label(self):
        d = self._write("jobs:\n  a:\n    runs-on: ubuntu-latest  # was self-hosted\n")
        self.assertEqual(
            chr.check(d), [("wf.yml", "runs-on: ubuntu-latest  # was self-hosted")]
        )

    def test_matrix_indirection_is_not_scanned(self):
        # The label comes from the matrix at run time, so a static scan
        # cannot resolve it; it is not a hosted reference.
        d = self._write("jobs:\n  a:\n    runs-on: ${{ matrix.runs_on }}\n")
        self.assertEqual(chr.check(d), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
