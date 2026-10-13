#!/usr/bin/env python3
"""Regression tests for scripts/check-compose-consolidation.py.

The AUT-3944 backup invariants (the `backup` GUI port binding, the hourly
offsite push target, and the offsite-enabled flag) were asserted only as prose
for a while, and were dropped outright by the PR #832 rewrite. Nothing tested
them, so either kind of regression would ship silently: the GUI binding could
widen off loopback, or the hourly push could keep addressing the retired
`autobrain-backup` DNS name and quietly stop.

AUT-6415: dongle-server and backup GUI merged into backend container.
Dongle-server runs on :8002, backup GUI runs on :8080 inside the backend container.

These tests drive the real script against the real compose file and against
deliberately broken copies of it, so the invariants are enforced by CI rather
than by memory.

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

    def test_services_count_is_seven(self):
        # AUT-6415: consolidated to 7 services (postgres, redis, minio, backend, frontend, hub, 9router)
        self.assertEqual(len(self.doc["services"]), 7)
        expected = {"postgres", "redis", "minio", "backend", "frontend", "hub", "9router"}
        self.assertEqual(set(self.doc["services"].keys()), expected)

    def test_dongle_server_merged_into_backend(self):
        # dongle-server should not be a separate service
        self.assertNotIn("dongle-server", self.doc["services"])
        # backend command should include dongle-server uvicorn
        cmd = self.doc["services"]["backend"]["command"]
        self.assertIn("dongle_server.main:app", cmd)
        # DONGLE_SERVER_URL should point to localhost:8002
        dongle_url = str(self.doc["services"]["backend"]["environment"]["DONGLE_SERVER_URL"])
        self.assertIn("localhost:8002", dongle_url)

    def test_backup_gui_merged_into_backend(self):
        # backup should not be a separate service
        self.assertNotIn("backup", self.doc["services"])
        # backend command should include backup GUI uvicorn
        cmd = self.doc["services"]["backend"]["command"]
        self.assertIn("backup_gui.main:app", cmd)
        # BACKUP_OFFSITE_URL should point to localhost:8080
        url = str(self.doc["services"]["backend"]["environment"]["BACKUP_OFFSITE_URL"])
        self.assertIn("localhost:8080", url)

    def test_offsite_enabled_is_true(self):
        enabled = self.doc["services"]["backend"]["environment"]["BACKUP_OFFSITE_ENABLED"]
        self.assertEqual(str(enabled).lower(), "true")

    def test_backend_exposes_all_ports(self):
        # backend should expose 8000 (API), 8001 (AI gateway), 8002 (dongle-server), 8080 (backup GUI)
        expose = self.doc["services"]["backend"].get("expose", [])
        self.assertIn("8000", expose)
        self.assertIn("8001", expose)
        self.assertIn("8002", expose)
        self.assertIn("8080", expose)


class TestComposeConsolidationBackupInvariants(unittest.TestCase):
    """Negative cases: each broken invariant must fail the check loudly."""

    def assert_fails_with(self, mutate_fn, expected):
        rc, out = run_check(broken(mutate_fn))
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL:", out)
        self.assertIn(expected, out)

    def test_dongle_server_service_reappears_fails(self):
        # Adding back dongle-server service should fail
        def mutate(doc):
            doc["services"]["dongle-server"] = {
                "image": "test:latest",
                "expose": ["8000"]
            }
        self.assert_fails_with(mutate, "retired `dongle-server` service is back")

    def test_backup_service_reappears_fails(self):
        # Adding back backup service should fail
        def mutate(doc):
            doc["services"]["backup"] = {
                "image": "test:latest",
                "ports": ["127.0.0.1:8080:8080"]
            }
        self.assert_fails_with(mutate, "retired `backup` service is back")

    def test_offsite_url_on_retired_dns_name_fails(self):
        self.assert_fails_with(
            backend_env(BACKUP_OFFSITE_URL="http://autobrain-backup:8080"),
            "BACKUP_OFFSITE_URL still points at the old dns name",
        )

    def test_offsite_url_targeting_backup_service_fails(self):
        self.assert_fails_with(
            backend_env(BACKUP_OFFSITE_URL="http://backup:8080"),
            "BACKUP_OFFSITE_URL should point to localhost, not `backup` service",
        )

    def test_offsite_url_not_localhost_fails(self):
        self.assert_fails_with(
            backend_env(BACKUP_OFFSITE_URL="http://someotherhost:8080"),
            "BACKUP_OFFSITE_URL should target localhost:8080",
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

    def test_dongle_server_url_not_localhost_fails(self):
        self.assert_fails_with(
            backend_env(DONGLE_SERVER_URL="http://dongle-server:8000"),
            "DONGLE_SERVER_URL should target localhost:8002",
        )


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

    def test_missing_celery_fails(self):
        doc_cmd = load_compose()["services"]["backend"]["command"]
        stripped = doc_cmd.replace("celery -A app.workers.celery_app:celery_app worker -B -l info --concurrency=2 &", "")
        rc, out = run_check(broken(set_backend_command(stripped)))
        self.assertEqual(rc, 1, out)
        self.assertIn("backend command missing Celery worker+beat", out)

    def test_missing_ai_gateway_fails(self):
        doc_cmd = load_compose()["services"]["backend"]["command"]
        stripped = doc_cmd.replace("uvicorn ai_app.main:app --host 0.0.0.0 --port 8001 &", "")
        rc, out = run_check(broken(set_backend_command(stripped)))
        self.assertEqual(rc, 1, out)
        self.assertIn("backend command missing the AI gateway uvicorn on :8001", out)

    def test_missing_dongle_server_fails(self):
        doc_cmd = load_compose()["services"]["backend"]["command"]
        stripped = doc_cmd.replace("uvicorn dongle_server.main:app --host 0.0.0.0 --port 8002 &", "")
        rc, out = run_check(broken(set_backend_command(stripped)))
        self.assertEqual(rc, 1, out)
        self.assertIn("backend command missing dongle-server uvicorn on :8002", out)

    def test_missing_backup_gui_fails(self):
        doc_cmd = load_compose()["services"]["backend"]["command"]
        stripped = doc_cmd.replace("uvicorn backup_gui.main:app --host 0.0.0.0 --port 8080 &", "")
        rc, out = run_check(broken(set_backend_command(stripped)))
        self.assertEqual(rc, 1, out)
        self.assertIn("backend command missing backup GUI uvicorn on :8080", out)


if __name__ == "__main__":
    unittest.main()