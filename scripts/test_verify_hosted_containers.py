#!/usr/bin/env python3
"""Tests for verify-hosted-containers.py and check-compose-consolidation.py (AUT-3908)."""
import importlib.util
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vhc = load("verify_hosted_containers", "verify-hosted-containers.py")


def container(stack, service, state="running"):
    return {
        "State": state,
        "Labels": {
            "com.docker.compose.project": stack,
            "com.docker.compose.service": service,
        },
    }


class TestRunningServices(unittest.TestCase):
    def test_only_counts_target_stack(self):
        containers = [
            container("autobrain-hosted", "backend"),
            container("other-stack", "backend"),
            {"State": "running", "Labels": {}},
        ]
        self.assertEqual(vhc.running_services(containers, "autobrain-hosted"), {"backend": "running"})

    def test_captures_state(self):
        containers = [container("s", "minio", state="exited")]
        self.assertEqual(vhc.running_services(containers, "s"), {"minio": "exited"})


class TestCompare(unittest.TestCase):
    def test_match(self):
        self.assertEqual(vhc.compare({"a", "b"}, {"a", "b"}), ([], []))

    def test_reports_missing_and_extra(self):
        self.assertEqual(
            vhc.compare({"a", "b"}, {"a", "c"}),
            (["b"], ["c"]),
        )


class TestComposeConsolidation(unittest.TestCase):
    def test_hosted_compose_satisfies_consolidation_invariants(self):
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "check-compose-consolidation.py")],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_consolidated_services_removed(self):
        self.assertFalse(
            {"worker", "ai", "market-data", "backup-agent"} & vhc.compose_services(),
            "consolidated services must not be back in docker-compose.hosted.yml")


if __name__ == "__main__":
    unittest.main()
