#!/usr/bin/env python3
"""Regression tests for the monotonic pin-bump guard (AUT-5669).

build-hosted.yml queues every push to main under
`concurrency: {cancel-in-progress: false}`, so a run for an older
commit can finish after a run for a newer commit and overwrite the
pinned digests with an older manifest. Pin bumps must therefore be
monotonic in commit order: a bump whose build SHA is a strict
ancestor of the SHA that produced the currently pinned digests must
no-op.

These tests run scripts/guard-compose-pin-monotonic.sh against a
throwaway git repo with a stubbed commit graph and assert the exit
code for the orderings that actually occurred.
"""
import os
import subprocess
import tempfile
import unittest

SCRIPT = "scripts/guard-compose-pin-monotonic.sh"
PATHSPEC = "docker-compose.hosted.yml"
COMMIT_MSG = "chore: bump hosted compose pins to freshly built digests [skip ci] build-sha {sha}\n"


def sha_of(repo: str, ref: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, "rev-parse", ref],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def commit(repo: str, message: str, file: str = PATHSPEC) -> str:
    """Commit `file` and return its SHA. `{sha}` in `message` is
    replaced with the commit's own SHA (via --amend), so a pin-bump
    commit can record the build SHA that produced it."""
    with open(os.path.join(repo, file), "a") as f:
        f.write("# bump\n")
    subprocess.run(["git", "-C", repo, "add", file], check=True)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", message],
                   check=True, capture_output=True, env=env)
    sha = sha_of(repo, "HEAD")
    if "{sha}" in message:
        subprocess.run(
            ["git", "-C", repo, "commit", "-q", "--amend", "-m",
             message.format(sha=sha)],
            check=True, capture_output=True, env=env)
    return sha


class GuardMonotonic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        subprocess.run(["git", "-C", self.repo, "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.name", "t"], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "user.email", "t@t"], check=True)
        with open(os.path.join(self.repo, PATHSPEC), "w") as f:
            f.write("services: {}\n")
        subprocess.run(["git", "-C", self.repo, "add", PATHSPEC], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-q", "-m", "root"],
                       check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def guard(self, build_sha: str) -> int:
        # The guard runs inside a throwaway repo (cwd=self.repo), so
        # resolve its real location relative to this test file.
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              os.path.basename(SCRIPT))
        return subprocess.run(
            ["bash", script, build_sha, PATHSPEC],
            cwd=self.repo, capture_output=True, text=True,
        ).returncode

    def test_no_prior_bump_is_fresh(self):
        sha = commit(self.repo, "root")
        self.assertEqual(self.guard(sha), 0)

    def test_same_sha_is_fresh(self):
        sha = commit(self.repo, COMMIT_MSG)
        self.assertEqual(self.guard(sha), 0)

    def test_newer_build_is_fresh(self):
        # build for an older commit pinned first, then a newer build
        old = commit(self.repo, "old")
        commit(self.repo, COMMIT_MSG)
        new = commit(self.repo, "new")
        self.assertEqual(self.guard(new), 0)

    def test_stale_older_build_is_rejected(self):
        # the AUT-5669 ordering: a newer commit's build lands first,
        # then the older commit's queued run finishes and tries to bump
        old = commit(self.repo, "old")
        new = commit(self.repo, "new")
        commit(self.repo, COMMIT_MSG)
        self.assertEqual(self.guard(old), 1)

    def test_two_steps_back_is_rejected(self):
        a = commit(self.repo, "a")
        b = commit(self.repo, "b")
        c = commit(self.repo, "c")
        commit(self.repo, COMMIT_MSG)
        self.assertEqual(self.guard(b), 1)
        self.assertEqual(self.guard(a), 1)

    def test_commit_without_build_sha_is_ignored(self):
        # auto-bump / version commits must not arm the guard
        sha = commit(self.repo, "chore: bump version to 1.2.3")
        self.assertEqual(self.guard(sha), 0)


if __name__ == "__main__":
    unittest.main()
