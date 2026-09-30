#!/usr/bin/env python3
"""Guard: scripts/post-deploy-smoke.sh signup payload matches the API contract.

AUT-4687 — the hosted smoke test posted {email, password}, the contract requires
{email, display_name}, so every deploy was reported as failed on healthy auth.
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(REPO, "backend", "app", "schemas", "auth.py")
SCRIPT = os.path.join(REPO, "scripts", "post-deploy-smoke.sh")

def _class_body(source: str, name: str) -> str:
    start = source.index(f"class {name}(")
    rest = source[start:]
    return rest[: rest.index("\nclass ")] if "\nclass " in rest else rest

class TestPostDeploySmokeSignupPayload(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(SCHEMA) as f:
            cls.schema = _class_body(f.read(), "SignupRequest")
        with open(SCRIPT) as f:
            cls.script = f.read()

    def test_payload_sends_every_required_field(self):
        payload = re.search(r'-d "\{(.*?)\}"', self.script)
        self.assertIsNotNone(payload, "signup payload not found in smoke script")
        sent = set(re.findall(r'\\?"([a-z_]+)\\?"\s*:', payload.group(1)))
        required = set(re.findall(r"^\s{4}(\w+):", self.schema, re.M))
        self.assertTrue(required)
        self.assertEqual(sent, required, f"payload {sent} != required {required}")

    def test_script_checks_the_signup_status_code(self):
        self.assertIn('if [ "$signup_code" = "201" ]', self.script)


if __name__ == "__main__":
    unittest.main()
