#!/usr/bin/env python3
"""AUT-4678: regression tests for check-compose-config.py.

Two guards:
1. the real docker-compose.hosted.yml passes (the script must not rot into a
   crash or a false FAIL the way it did on main before AUT-4678);
2. a compose file whose optional services are absent is handled with a
   presence check, not an unconditional index (no KeyError).
"""
import importlib.util
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "check-compose-config.py")

spec = importlib.util.spec_from_file_location("check_compose_config", SCRIPT)
ccc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ccc)


class TestHostedComposePasses(unittest.TestCase):
    def test_script_exits_zero_on_main_compose(self):
        r = subprocess.run(
            [sys.executable, SCRIPT], cwd=REPO, capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        self.assertIn("OK: docker-compose.hosted.yml", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


class TestOptionalServices(unittest.TestCase):
    def test_present_filters_absent_services(self):
        svcs = {"backend": {}, "postgres": {}}
        self.assertEqual(ccc.present(svcs, ("backend", "ai")), ["backend"])
        self.assertEqual(ccc.present(svcs, ("backend", "postgres")), ["backend", "postgres"])
        self.assertEqual(ccc.present({}, ("backend",)), [])

    def test_env_of_tolerates_missing_service(self):
        self.assertEqual(ccc.env_of(None), {})


class TestSecretFileSet(unittest.TestCase):
    def test_offsite_backup_keys_are_known_secrets(self):
        self.assertIn("backup_offsite_gui_key", ccc.SECRET_FILES)
        self.assertIn("backup_offsite_ingest_key", ccc.SECRET_FILES)

    def test_every_file_ref_in_hosted_compose_is_a_known_secret(self):
        import yaml
        with open(os.path.join(REPO, "docker-compose.hosted.yml")) as f:
            svcs = yaml.safe_load(f)["services"]
        unknown = []
        for name in ccc.present(svcs, ccc.SECRET_SERVICES):
            for k, v in ccc.env_of(svcs[name]).items():
                if k.endswith("_FILE") and str(v).rsplit("/", 1)[-1] not in ccc.SECRET_FILES:
                    unknown.append(f"{name}:{k}")
        self.assertEqual(unknown, [])

class TestPlainSecretScan(unittest.TestCase):
    """AUT-5530: plaintext key material in any compose file is a FAIL."""

    def test_shape_matcher_finds_the_aut_5530_key(self):
        # synthetic value — never the real (now-revoked) key material
        svcs = {"rego-lookup": {"environment": {
            "ENVIRONMENT": "development",
            "API_KEY": "unit-test-key-not-real-material",
        }}}
        self.assertEqual(
            ccc.plain_secrets(svcs), {"rego-lookup": ["API_KEY"]})

    def test_backend_plain_rego_key_is_flagged(self):
        svcs = {"backend": {"environment": {
            "REGO_LOOKUP_API_KEY": "x" * 40,
        }}}
        self.assertEqual(
            ccc.plain_secrets(svcs), {"backend": ["REGO_LOOKUP_API_KEY"]})

    def test_interpolation_and_non_secret_keys_are_not_flagged(self):
        svcs = {"frontend": {"environment": {
            "SOCIAL_FEDERATION_HUB_URL": "${SOCIAL_FEDERATION_HUB_URL:-x}",
            "LOGIN_MAX_ATTEMPTS": "5",
            "API_KEY_FILE": "/run/secrets/rego_lookup_api_key",
            "REGO_LOOKUP_API_KEY_FILE": "/run/secrets/rego_lookup_api_key",
        }}}
        self.assertEqual(ccc.plain_secrets(svcs), {})

    def test_every_compose_file_in_repo_is_clean(self):
        import glob
        import yaml
        dirty = []
        for path in sorted(glob.glob(os.path.join(REPO, "docker-compose*.yml"))):
            with open(path) as f:
                doc = yaml.safe_load(f) or {}
            dirty += [f"{os.path.basename(path)}:{n}:{k}"
                      for n, ks in ccc.plain_secrets(doc.get("services") or {}).items()
                      for k in ks]
        self.assertEqual(dirty, [])



if __name__ == "__main__":
    unittest.main()
