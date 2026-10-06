#!/usr/bin/env python3
"""AUT-5686: regression tests for scripts/check_demo_compose.py.

The gate had two rot bugs:
1. it took two positional args (compose + env file) and crashed with
   IndexError when the CI workflow ran it bare — so the guard never ran.
2. it had no assertion that DEMO_PASSWORD is required, so a tier could be
   redeployed with the burned code default and pass the gate.

These tests cover the no-arg path, the required-DEMO_PASSWORD invariant, and
the no-literal-credential invariant.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check_demo_compose.py")
COMPOSE = os.path.join(REPO, "docker-compose.demo.yml")

spec = importlib.util.spec_from_file_location("check_demo_compose", SCRIPT)
cdc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdc)

# A minimal env file that satisfies every ${VAR:?...} in the compose. The real
# .env.example has 119 keys; this one only needs the required ones.
ENV = "\n".join([
    "DEMO_PASSWORD=change-me-demo-password",
    "POSTGRES_PASSWORD=change-me-postgres-password",
    "SECRET_KEY=change-me-secret-key",
    "MINIO_ACCESS_KEY=change-me-minio-access-key",
    "MINIO_SECRET_KEY=change-me-minio-secret-key",
    "AI_GATEWAY_API_KEY=change-me-ai-gateway-key",
    "AI_ROUTER_API_KEY=change-me-ai-router-key",
    "MARKET_DATA_API_KEY=change-me-market-data-key",
    "REGO_LOOKUP_API_KEY=change-me-rego-lookup-key",
]) + "\n"


class TestNoArgRuns(unittest.TestCase):
    def test_bare_invocation_exits_zero(self):
        r = subprocess.run(
            [sys.executable, SCRIPT], cwd=REPO, capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        self.assertIn("OK: docker-compose.demo.yml is deployable", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


class TestDemoPasswordRequired(unittest.TestCase):
    def test_missing_demo_password_fails(self):
        text = open(COMPOSE).read()
        # strip the DEMO_PASSWORD line out of the backend env
        import re
        bad = re.sub(r'\n\s*DEMO_PASSWORD:.*\n', '\n', text, count=1)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.yml")
            open(p, "w").write(bad)
            e = os.path.join(d, "e.env")
            open(e, "w").write(ENV)
            r = subprocess.run([sys.executable, SCRIPT, p, e],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn("DEMO_PASSWORD", r.stdout)

    def test_defaulted_demo_password_fails(self):
        text = open(COMPOSE).read()
        bad = text.replace(
            'DEMO_PASSWORD: "${DEMO_PASSWORD:?DEMO_PASSWORD must be set in .env (secret: demo/demo-account-password)}"',
            'DEMO_PASSWORD: "${DEMO_PASSWORD:-demo}"',
        )
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.yml")
            open(p, "w").write(bad)
            e = os.path.join(d, "e.env")
            open(e, "w").write(ENV)
            r = subprocess.run([sys.executable, SCRIPT, p, e],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn("DEMO_PASSWORD", r.stdout)


class TestNoLiteralCredential(unittest.TestCase):
    def test_literal_demo_password_in_compose_fails(self):
        text = open(COMPOSE).read()
        # inject the burned credential into a comment (the regression AUT-5582
        # reintroduced: a header line carrying the email + password). The
        # header wraps across two lines, so append a fresh comment line rather
        # than trying to splice the wrap.
        bad = text + "\n# legacy: demo@autobrainservice.app / demo\n"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.yml")
            open(p, "w").write(bad)
            e = os.path.join(d, "e.env")
            open(e, "w").write(ENV)
            r = subprocess.run([sys.executable, SCRIPT, p, e],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn("literal demo credential", r.stdout)


if __name__ == "__main__":
    unittest.main()