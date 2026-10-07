#!/usr/bin/env python3
"""AUT-5766: regression tests for check_demo_compose.py.

Guards:
1. the real docker-compose.demo.yml passes (the script must not rot into a
   crash or a false FAIL);
2. DEMO_PASSWORD is required (not optional, not literal);
3. no literal demo credential anywhere in the compose.
"""
import importlib.util
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check_demo_compose.py")

spec = importlib.util.spec_from_file_location("check_demo_compose", SCRIPT)
cdc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cdc)


class TestDemoComposePasses(unittest.TestCase):
    def test_script_exits_zero_on_demo_compose(self):
        r = subprocess.run(
            [sys.executable, SCRIPT], cwd=REPO, capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        self.assertIn("OK: docker-compose.demo.yml", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


class TestDemoPasswordRequired(unittest.TestCase):
    def test_demo_password_is_required_var(self):
        import yaml
        with open(os.path.join(REPO, "docker-compose.demo.yml")) as f:
            doc = yaml.safe_load(f)
        backend_env = doc["services"]["backend"]["environment"]
        demo_pw = backend_env.get("DEMO_PASSWORD", "")
        self.assertTrue(
            str(demo_pw).startswith("${DEMO_PASSWORD:?"),
            f"DEMO_PASSWORD must be a required var, got: {demo_pw!r}"
        )


class TestNoLiteralDemoCredential(unittest.TestCase):
    def test_no_literal_demo_password_in_compose(self):
        with open(os.path.join(REPO, "docker-compose.demo.yml")) as f:
            text = f.read()
        # Check for common literal patterns
        self.assertNotRegex(text, r"demo\s*/\s*demo", "found demo/demo literal")
        self.assertNotRegex(text, r"password\s*[=:]\s*demo\b", "found password=demo")
        self.assertNotRegex(text, r"DEMO_PASSWORD\s*[=:]\s*['\"]?demo\b", "found DEMO_PASSWORD=demo")


if __name__ == "__main__":
    unittest.main()
