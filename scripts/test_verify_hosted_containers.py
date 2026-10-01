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


RUNNER_COMPANION = "gh-runner-autobrain-arm64/gh-runner-autobrain-arm64=gh-runner"


class TestParseCompanion(unittest.TestCase):
    def test_parses_stack_service_declared(self):
        self.assertEqual(
            vhc.parse_companion(RUNNER_COMPANION),
            ("gh-runner-autobrain-arm64", "gh-runner-autobrain-arm64", "gh-runner"),
        )

    def test_rejects_malformed_spec(self):
        for bad in ("nonsense", "stack=", "/svc=declared", "stack/svc=", "stack/svc"):
            with self.assertRaises(ValueError):
                vhc.parse_companion(bad)


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

    def test_companion_stack_resolves_declared_name(self):
        # AUT-4725: gh-runner is declared in the hosted compose but Portainer runs
        # it as its own stack under a different service name.
        containers = [
            container("autobrain-hosted", "backend"),
            container("gh-runner-autobrain-arm64", "gh-runner-autobrain-arm64"),
        ]
        self.assertEqual(
            vhc.running_services(containers, "autobrain-hosted", [RUNNER_COMPANION]),
            {"backend": "running", "gh-runner": "running"},
        )

    def test_companion_not_counted_without_spec(self):
        containers = [container("gh-runner-autobrain-arm64", "gh-runner-autobrain-arm64")]
        self.assertEqual(vhc.running_services(containers, "autobrain-hosted"), {})

    def test_main_stack_wins_over_companion(self):
        containers = [
            container("autobrain-hosted", "gh-runner", state="running"),
            container("gh-runner-autobrain-arm64", "gh-runner-autobrain-arm64", state="exited"),
        ]
        self.assertEqual(
            vhc.running_services(containers, "autobrain-hosted", [RUNNER_COMPANION]),
            {"gh-runner": "running"},
        )

    def test_companion_stopped_service_reported_not_running(self):
        containers = [
            container("gh-runner-autobrain-arm64", "gh-runner-autobrain-arm64", state="exited"),
        ]
        self.assertEqual(
            vhc.running_services(containers, "autobrain-hosted", [RUNNER_COMPANION]),
            {"gh-runner": "exited"},
        )


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

    def test_declared_companion_defaults_resolve_against_real_compose(self):
        # Every default companion must name a service that compose actually
        # declares, otherwise a typo silently turns into a MISSING failure.
        declared = vhc.compose_services()
        for spec in vhc.DEFAULT_COMPANION_STACKS:
            _, _, declared_name = vhc.parse_companion(spec)
            self.assertIn(declared_name, declared,
                          f"companion {spec} does not map to a declared service")


if __name__ == "__main__":
    unittest.main()
