#!/usr/bin/env python3
"""Regression tests for sync-compose-to-portainer.py.

Three behaviours that each took a production incident to pin down:

* log output must not leak the API response body (secret hygiene);
* stack env must be read from GET /api/stacks/{id}, never /file — reading it
  from /file sent Env: [] and wiped all stack env vars (AUT-4778), which made
  Portainer fail compose interpolation with HTTP 500;
* a 200 PUT is not a healthy stack — a host-port orphan must block the PUT and
  an unhealthy result after the PUT must fail the job (AUT-4911, AUT-4946);
* a healthy stack is not a deployed one — the running image digest and container
  command must match the compose, because an inline stack re-pulls the same
  immutable digest and reports success without shipping code (AUT-5132).

Mocks are routed by URL rather than by call order: the script makes a variable
number of calls (the health poll repeats), and an ordered list silently went
stale the moment PR #852 added the verification calls.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "sync_compose_to_portainer",
    os.path.join(os.path.dirname(__file__), "sync-compose-to-portainer.py"),
)
scp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scp)

STACKS = [{"Id": 42, "Name": "autobrain-hosted"}]

BACKEND_REF = "ghcr.io/x/backend:hosted@sha256:" + "a" * 64
FRONTEND_REF = "ghcr.io/x/frontend:hosted@sha256:" + "b" * 64
OLD_BACKEND_DIGEST = "ghcr.io/x/backend@sha256:" + "c" * 64


class _Args:
    """Minimal stand-in for the parsed argparse namespace."""
    endpoint = 5
    api_key = "test-key"
    portainer_url = "https://portainer.example.com"


def _container(name, service, state="running", ports=(), command=None):
    return {
        "Id": f"cid-{service}",
        "Image": f"sha256:{service}",
        "Names": ["/" + name],
        "State": state,
        "Status": f"Up (mock) {state}",
        "Labels": {"com.docker.compose.service": service},
        "Ports": [{"PublicPort": p} for p in ports],
        "_command": command,
    }


class _Responder:
    """Serve canned JSON by (method, path substring)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, req, timeout=None):
        method = getattr(req, "method", None) or "GET"
        url = req.full_url
        self.calls.append((method, url, req.data))
        # Longest fragment first: "/api/stacks/42" must win over "/api/stacks".
        for (route_method, fragment), payload in sorted(
                self.routes.items(), key=lambda kv: -len(kv[0][1])):
            if route_method == method and fragment in url:
                body = json.dumps(payload).encode()
                return contextlib.nullcontext(_FakeResponse(body))
        raise AssertionError(f"unexpected {method} {url}")

    def urls(self, method=None):
        return [u for (m, u, _) in self.calls if method is None or m == method]

    def methods_for(self, fragment):
        """Methods used against any URL containing fragment."""
        return [m for (m, u, _) in self.calls if fragment in u]

    def last_body(self, method):
        for (m, _, data) in reversed(self.calls):
            if m == method and data is not None:
                return json.loads(data)
        raise AssertionError(f"no {method} body recorded")


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class SyncComposeTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.compose_file = os.path.join(self.tmp, "docker-compose.hosted.yml")
        self.write_compose(command=None)

    def write_compose(self, command=None):
        cmd = (f"    command: {json.dumps(command)}\n" if command else "")
        with open(self.compose_file, "w") as f:
            f.write("version: '3.8'\nservices:\n"
                    f"  backend:\n    image: {BACKEND_REF}\n{cmd}"
                    "    ports:\n      - \"8000:8000\"\n"
                    f"  frontend:\n    image: {FRONTEND_REF}\n"
                    "    ports:\n      - \"80:80\"\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_main(self, responder, extra_args=()):
        """Run main() with urlopen routed by responder; returns (rc, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        argv = ["sync-compose-to-portainer.py",
                "--stack", "autobrain-hosted",
                "--endpoint", "5",
                "--file", self.compose_file,
                "--portainer-url", "https://portainer.example.com",
                "--api-key", "test-key", *extra_args]
        old_argv, old_out, old_err = sys.argv, sys.stdout, sys.stderr
        sys.argv, sys.stdout, sys.stderr = argv, out, err
        try:
            with patch("urllib.request.urlopen", responder):
                rc = scp.main()
        finally:
            sys.argv, sys.stdout, sys.stderr = old_argv, old_out, old_err
        return rc, out.getvalue(), err.getvalue()

    def healthy_routes(self, containers, backend_digest=None, command=None):
        """Routes for a stack that matches the compose written by setUp."""
        backend_digest = backend_digest or BACKEND_REF.split("@", 1)[1]
        frontend_digest = FRONTEND_REF.split("@", 1)[1]
        return {
            ("GET", "/api/stacks"): STACKS,
            ("GET", "/api/stacks/42"): {"Id": 42, "Env": [
                {"name": "POSTGRES_USER", "value": "autobrain"}]},
            ("GET", "/docker/containers/json"): containers,
            ("GET", "/docker/containers/cid-backend/json"): {"Config": {
                "Cmd": ["/bin/sh", "-c", command] if command else []}},
            ("GET", "/docker/images/sha256:backend"): {"RepoDigests": [
                f"ghcr.io/x/backend@{backend_digest}"]},
            ("GET", "/docker/images/sha256:frontend"): {"RepoDigests": [
                f"ghcr.io/x/frontend@{frontend_digest}"]},
            ("PUT", "/api/stacks/42"): {"Id": 42},
        }


class TestLogHygiene(SyncComposeTestBase):

    def test_log_output_excludes_response_body(self):
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))
        r.routes[("PUT", "/api/stacks/42")] = {
            "Id": 42, "SomeSensitiveData": "should-not-appear-in-logs"}

        rc, out, _ = self.run_main(r)

        self.assertEqual(rc, 0)
        self.assertIn("stack=autobrain-hosted", out)
        self.assertIn("id=42", out)
        self.assertIn("endpoint=5", out)
        self.assertNotIn("SomeSensitiveData", out)
        self.assertNotIn("should-not-appear-in-logs", out)


class TestEnvPreservation(SyncComposeTestBase):

    def test_env_read_from_stack_detail_not_file(self):
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))

        rc, _, _ = self.run_main(r)

        self.assertEqual(rc, 0)
        self.assertIn("https://portainer.example.com/api/stacks/42", r.urls())
        for url in r.urls():
            self.assertNotIn("/api/stacks/42/file", url)
        self.assertEqual(r.last_body("PUT")["Env"],
                         [{"name": "POSTGRES_USER", "value": "autobrain"}])

    def test_refuses_to_sync_when_env_empty(self):
        routes = self.healthy_routes([])
        routes[("GET", "/api/stacks/42")] = {"Id": 42, "Env": []}
        r = _Responder(routes)

        rc, _, err = self.run_main(r)

        self.assertEqual(rc, 3)
        self.assertIn("would wipe it", err)
        self.assertNotIn("PUT", r.methods_for("/api/stacks/42"))


class TestPortCollisionGuard(SyncComposeTestBase):
    """AUT-4946: an orphan holding a port the new compose needs blocks the PUT."""

    def test_refuses_put_when_orphan_holds_wanted_port(self):
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend", ports=[8000]),
            _container("autobrain-hosted-frontend-1", "frontend", ports=[80]),
            _container("autobrain-ghost-1", "ghost", ports=[80]),
        ]))

        rc, _, err = self.run_main(r)

        self.assertEqual(rc, 5)
        self.assertIn("port collision", err)
        self.assertIn("autobrain-ghost-1", err)
        self.assertNotIn("PUT", r.methods_for("/api/stacks/42"))


class TestPostUpdateHealthGate(SyncComposeTestBase):
    """AUT-4946: a 200 PUT followed by unhealthy containers must fail the job."""

    def test_fails_when_a_service_never_starts(self):
        # backend missing, frontend up. verify_running is patched to avoid
        # sleeping through its 20 x 5s poll.
        containers = [_container("autobrain-hosted-frontend-1", "frontend")]
        r = _Responder(self.healthy_routes(containers))

        with patch.object(scp, "verify_running", return_value=[
                (None, "service 'backend' has no running container")]):
            rc, _, err = self.run_main(r)

        self.assertEqual(rc, 6)
        self.assertIn("NOT healthy", err)
        self.assertIn("backend", err)
        self.assertIn("PUT", r.methods_for("/api/stacks/42"))

    def test_succeeds_when_all_services_running(self):
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))

        with patch.object(scp, "verify_running", return_value=[]):
            rc, out, _ = self.run_main(r)

        self.assertEqual(rc, 0)
        self.assertIn("verified:", out)


class TestNoopDeployDetection(SyncComposeTestBase):
    """AUT-5132: a healthy stack on the wrong image/command is a failed deploy."""

    def _containers(self):
        return [_container("autobrain-hosted-backend-1", "backend"),
                _container("autobrain-hosted-frontend-1", "frontend")]

    def test_fails_when_running_digest_is_not_the_pinned_one(self):
        r = _Responder(self.healthy_routes(self._containers(),
                                           backend_digest=OLD_BACKEND_DIGEST))

        rc, _, err = self.run_main(r)

        self.assertEqual(rc, 7)
        self.assertIn("deploy did not land", err)
        self.assertIn("no-op", err)
        self.assertIn("autobrain-hosted-backend-1", err)

    def test_succeeds_when_digests_match(self):
        r = _Responder(self.healthy_routes(self._containers()))

        rc, out, _ = self.run_main(r)

        self.assertEqual(rc, 0)
        self.assertIn("image digests", out)

    def test_fails_when_container_command_is_stale(self):
        self.write_compose(command="sh -c \"alembic upgrade head\"")
        r = _Responder(self.healthy_routes(self._containers(),
                                           command="sh -c \"./old.sh\""))

        rc, _, err = self.run_main(r)

        self.assertEqual(rc, 7)
        self.assertIn("command is", err)
        self.assertIn("sh -c alembic upgrade head", err)

    def test_unpinned_image_is_not_asserted_on(self):
        with open(self.compose_file, "w") as f:
            f.write("services:\n  backend:\n    image: ghcr.io/x/backend:hosted\n")
        r = _Responder(self.healthy_routes(self._containers()))

        rc, _, _ = self.run_main(r)

        self.assertEqual(rc, 0)  # no digest declared -> the tag is the contract

    def test_interpolates_stack_env_before_comparing(self):
        """$$ must be compared as $, else every well-formed stack looks stale."""
        # healthy_routes wraps `command` in ["/bin/sh","-c",command], so the
        # compose side spells the same argv explicitly.
        self.write_compose(command='/bin/sh -c "echo $$REDIS_PASSWORD"')
        r = _Responder(self.healthy_routes(self._containers(),
                                           command="echo $REDIS_PASSWORD"))

        rc, out, err = self.run_main(r)

        self.assertEqual(rc, 0, err)
        self.assertIn("image digests", out)

    def test_defaulted_var_is_interpolated_from_the_compose_default(self):
        self.write_compose(command='/bin/sh -c "echo ${NOPE:-fallback}"')
        r = _Responder(self.healthy_routes(self._containers(),
                                           command="echo fallback"))

        rc, _, err = self.run_main(r)

        self.assertEqual(rc, 0, err)

    def test_verify_only_does_not_put(self):
        r = _Responder(self.healthy_routes(self._containers()))

        rc, out, _ = self.run_main(r, extra_args=["--verify-only"])

        self.assertEqual(rc, 0)
        self.assertNotIn("PUT", r.methods_for("/api/stacks/42"))
        self.assertIn("verified", out)

    def test_verify_only_reports_drift_without_touching_the_stack(self):
        r = _Responder(self.healthy_routes(self._containers(),
                                           backend_digest=OLD_BACKEND_DIGEST))

        rc, _, err = self.run_main(r, extra_args=["--verify-only"])

        self.assertEqual(rc, 7)
        self.assertNotIn("PUT", r.methods_for("/api/stacks/42"))


class TestVerifyRunning(SyncComposeTestBase):
    """The poll itself, driven by fake container state rather than a stub."""

    def test_missing_service_reported(self):
        r = _Responder({("GET", "/docker/containers/json"): [
            _container("autobrain-hosted-frontend-1", "frontend")]})
        args = _Args()

        with patch("urllib.request.urlopen", r):
            problems = scp.verify_running(args, {"backend", "frontend"},
                                          attempts=1, delay=0)

        self.assertEqual(len(problems), 1)
        self.assertIn("backend", problems[0][1])

    def test_created_container_counts_as_stuck(self):
        r = _Responder({("GET", "/docker/containers/json"): [
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
            _container("autobrain-hosted-worker-1", "worker", state="created"),
        ]})
        args = _Args()

        with patch("urllib.request.urlopen", r):
            problems = scp.verify_running(args, {"backend", "frontend"},
                                          attempts=1, delay=0)

        self.assertEqual([w for _, w in problems if "stuck" in w],
                         ["stuck in state created"])


if __name__ == "__main__":
    unittest.main()
