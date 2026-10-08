#!/usr/bin/env python3
"""Regression tests for scripts/check-compose-consolidation.py.

The AUT-3944 backup invariants (the `backup` GUI port binding, the hourly
offsite push target, and the offsite-enabled flag) were asserted only as prose
for a while, and were dropped outright by the PR #832 rewrite. Nothing tested
them, so either kind of regression would ship silently: the GUI binding could
widen off loopback, or the hourly push could keep addressing the retired
`autobrain-backup` DNS name and quietly stop.

These tests drive the real script against the real compose file and against
deliberately broken copies of it, so the invariants are enforced by CI rather
than by memory. A final pair asserts the trigger that makes CI run them at all
(AUT-5069: the compose file was not in ci-tests.yml's `paths:` filter).

Run: python3 -m unittest scripts/test_check_compose_consolidation.py -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check-compose-consolidation.py")
COMPOSE = os.path.join(REPO, "docker-compose.hosted.yml")
CI_WORKFLOW = os.path.join(REPO, ".github", "workflows", "ci-tests.yml")

def load_compose():
    with open(COMPOSE) as f:
        return yaml.safe_load(f)

def run_check(compose_text=None):
    """Run the consolidation check and return (returncode, combined output).

    compose_text=None runs it against the real docker-compose.hosted.yml.
    Otherwise the text is written into a temp dir that becomes the cwd, so the
    script resolves COMPOSE against the broken copy.
    """
    tmp = None
    if compose_text is None:
        cwd = REPO
    else:
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "docker-compose.hosted.yml"), "w") as f:
            f.write(compose_text)
        cwd = tmp
    try:
        proc = subprocess.run(
            [sys.executable, SCRIPT], cwd=cwd, capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

def broken(mutate):
    """Return YAML text for the real compose file with `mutate` applied."""
    doc = load_compose()
    mutate(doc)
    return yaml.safe_dump(doc)

def backend_env(**changes):
    """Mutator: set keys on backend.environment."""
    def apply(doc):
        doc["services"]["backend"]["environment"].update(changes)
    return apply

def drop_backend_env(*keys):
    """Mutator: remove keys from backend.environment."""
    def apply(doc):
        env = doc["services"]["backend"]["environment"]
        for key in keys:
            env.pop(key, None)
    return apply

def set_backup_ports(ports):
    """Mutator: replace the backup service's port bindings."""
    def apply(doc):
        svc = doc["services"]["backup"]
        if ports is None:
            svc.pop("ports", None)
        else:
            svc["ports"] = ports
    return apply

def drop_backup_service(doc):
    del doc["services"]["backup"]

def set_backend_command(cmd):
    """Mutator: replace the backend container command."""
    def apply(doc):
        doc["services"]["backend"]["command"] = cmd
    return apply

class TestComposeConsolidationRealFile(unittest.TestCase):
    """The live compose file must satisfy every asserted invariant."""

    def setUp(self):
        self.rc, self.out = run_check()
        self.doc = load_compose()

    def test_check_passes_on_real_compose(self):
        self.assertEqual(self.rc, 0, self.out)
        self.assertIn("OK:", self.out)

    def test_backup_service_present(self):
        self.assertIn("backup", self.doc["services"])

    def test_backup_gui_port_bound_to_loopback_8080(self):
        ports = [str(p) for p in (self.doc["services"]["backup"].get("ports") or [])]
        self.assertTrue(
            any(p.endswith(":8080") and p.startswith("127.0.0.1:") for p in ports),
            f"backup GUI must stay on 127.0.0.1:8080, got {ports}",
        )

    def test_offsite_url_targets_backup_service(self):
        url = str(self.doc["services"]["backend"]["environment"]["BACKUP_OFFSITE_URL"])
        self.assertIn("backup:", url)
        self.assertNotIn("autobrain-backup:", url)

    def test_offsite_enabled_is_true(self):
        enabled = self.doc["services"]["backend"]["environment"]["BACKUP_OFFSITE_ENABLED"]
        self.assertEqual(str(enabled).lower(), "true")

class TestComposeConsolidationBackupInvariants(unittest.TestCase):
    """Negative cases: each broken invariant must fail the check loudly."""

    def assert_fails_with(self, mutate_fn, expected):
        rc, out = run_check(broken(mutate_fn))
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL:", out)
        self.assertIn(expected, out)

    def test_missing_backup_service_fails(self):
        self.assert_fails_with(
            drop_backup_service, "`backup` service missing (AUT-3944)"
        )

    def test_backup_port_off_loopback_fails(self):
        self.assert_fails_with(
            set_backup_ports(["0.0.0.0:8080:8080"]),
            "`backup` GUI port binding changed",
        )

    def test_backup_port_dropped_fails(self):
        self.assert_fails_with(
            set_backup_ports(None), "`backup` GUI port binding changed"
        )

    def test_backup_port_moved_off_8080_fails(self):
        self.assert_fails_with(
            set_backup_ports(["127.0.0.1:9090:9090"]),
            "`backup` GUI port binding changed",
        )

    def test_offsite_url_on_retired_dns_name_fails(self):
        self.assert_fails_with(
            backend_env(BACKUP_OFFSITE_URL="http://autobrain-backup:8080"),
            "BACKUP_OFFSITE_URL still points at the old dns name",
        )

    def test_offsite_url_not_targeting_backup_fails(self):
        self.assert_fails_with(
            backend_env(BACKUP_OFFSITE_URL="http://localhost:8080"),
            "BACKUP_OFFSITE_URL does not target the `backup` service",
        )

    def test_offsite_url_absent_fails(self):
        self.assert_fails_with(
            drop_backend_env("BACKUP_OFFSITE_URL"),
            "BACKUP_OFFSITE_URL does not target the `backup` service",
        )

    def test_offsite_disabled_fails(self):
        self.assert_fails_with(
            backend_env(BACKUP_OFFSITE_ENABLED="false"),
            'BACKUP_OFFSITE_ENABLED must stay "true"',
        )

    def test_offsite_enabled_absent_fails(self):
        self.assert_fails_with(
            drop_backend_env("BACKUP_OFFSITE_ENABLED"),
            'BACKUP_OFFSITE_ENABLED must stay "true"',
        )

class TestComposeConsolidationIsTriggered(unittest.TestCase):
    """The invariants above are only enforced if CI runs on the file they read.

    AUT-5069: `docker-compose.hosted.yml` was absent from ci-tests.yml's
    `paths:` filters, so a PR touching only the hosted compose file skipped
    the release-scripts job entirely and the AUT-3944 invariants went
    unenforced for exactly the file they guard.
    """

    def setUp(self):
        with open(CI_WORKFLOW) as f:
            doc = yaml.safe_load(f)
        # YAML 1.1 parses a bare `on:` key as the boolean True.
        self.on = doc.get("on", doc.get(True))
        self.assertIsNotNone(self.on, "ci-tests.yml has no trigger block")

    def test_pull_request_triggered_by_hosted_compose(self):
        self.assertIn("docker-compose.hosted.yml", self.on["pull_request"]["paths"])

    def test_push_to_main_triggered_by_hosted_compose(self):
        self.assertIn("docker-compose.hosted.yml", self.on["push"]["paths"])

class TestComposeConsolidationMigrations(unittest.TestCase):
    """AUT-5088: the backend must run `alembic upgrade head` before it serves.

    Hosted booted straight into `python -m app.db.bootstrap`, whose create_all
    fallback swallowed every migration failure, so migration-only changes (new
    index, constraint, column rename, data backfill) never ran in production.
    """

    def setUp(self):
        self.rc, self.out = run_check()
        self.doc = load_compose()

    def test_alembic_runs_before_bootstrap_in_backend_command(self):
        cmd = self.doc["services"]["backend"]["command"]
        self.assertIn("alembic upgrade head", cmd)
        self.assertLess(
            cmd.index("alembic upgrade head"), cmd.index("python -m app.db.bootstrap")
        )

    def test_missing_alembic_fails(self):
        doc_cmd = load_compose()["services"]["backend"]["command"]
        stripped = doc_cmd.replace("alembic upgrade head && ", "")
        rc, out = run_check(broken(set_backend_command(stripped)))
        self.assertEqual(rc, 1, out)
        self.assertIn("`alembic upgrade head` (AUT-5088)", out)

    def test_alembic_after_bootstrap_fails(self):
        doc_cmd = load_compose()["services"]["backend"]["command"]
        reordered = doc_cmd.replace(
            "alembic upgrade head && python -m app.db.bootstrap",
            "python -m app.db.bootstrap && alembic upgrade head",
        )
        rc, out = run_check(broken(set_backend_command(reordered)))
        self.assertEqual(rc, 1, out)
        self.assertIn("must run before bootstrap/uvicorn (AUT-5088)", out)


if __name__ == "__main__":
    unittest.main()
