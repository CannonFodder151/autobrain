#!/usr/bin/env python3
"""Regression tests for sync-compose-to-portainer.py.

Three behaviours that each took a production incident to pin down:

* log output must not leak the API response body (secret hygiene);
* stack env must be read from GET /api/stacks/{id}, never /file — reading it
  from /file sent Env: [] and wiped all stack env vars (AUT-4778), which made
  Portainer fail compose interpolation with HTTP 500;
* a 200 PUT is not a healthy stack — a host-port orphan must block the PUT and
  an unhealthy result after the PUT must fail the job (AUT-4911, AUT-4946);
* a healthy stack is not a deployed one — the running image digest and
  container command must match the compose, because an inline stack re-pulls
  the same immutable digest and reports success without shipping code
  (AUT-5132).

Mocks are routed by URL rather than by call order: the script makes a variable
number of calls (the health poll repeats), and an ordered list silently went
stale the moment PR #852 added the verification calls.
"""
import contextlib
import email
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "sync_compose_to_portainer",
    os.path.join(os.path.dirname(__file__), "sync-compose-to-portainer.py"),
)
scp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scp)

STACKS = [{"Id": 42, "Name": "autobrain-hosted"}]

# Full 64-hex digests: verify_image_digests compares repo@digest, so a
# truncated "sha256:aaa" fixture would never match a real RepoDigest.
BACKEND_REF = "ghcr.io/x/backend:hosted@sha256:" + "a" * 64
FRONTEND_REF = "ghcr.io/x/frontend:hosted@sha256:" + "b" * 64
OLD_BACKEND_DIGEST = "ghcr.io/x/backend@sha256:" + "c" * 64


class _Args:
    """Minimal stand-in for the parsed argparse namespace."""
    endpoint = 5
    api_key = "test-key"
    portainer_url = "https://portainer.example.com"


def _container(name, service, state="running", ports=()):
    return {
        "Id": f"cid-{service}" if service else "cid-foreign",
        "Image": f"sha256:{service}" if service else "sha256:foreign",
        "Names": ["/" + name],
        "State": state,
        "Status": f"Up (mock) {state}",
        "Labels": ({"com.docker.compose.service": service} if service
                   else {"autobrain.role": "verify-once"}),
        "Ports": [{"PublicPort": p} for p in ports],
    }


class _Responder:
    """Serve canned JSON by (method, path substring)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.call_headers = []

    def __call__(self, req, timeout=None):
        method = getattr(req, "method", None) or "GET"
        url = req.full_url
        self.calls.append((method, url, req.data))
        self.call_headers.append((method, url, dict(req.headers)))
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

    def headers_for(self, method, fragment):
        for (m, u, h) in reversed(self.call_headers):
            if m == method and fragment in u:
                return h
        raise AssertionError(f"no {method} to {fragment}")

    def last_raw_body(self, method):
        """Undecoded request body (for multipart posts)."""
        for (m, _, data) in reversed(self.calls):
            if m == method and data is not None:
                return data
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


def _multipart_fields(body, content_type):
    """Parse a multipart/form-data body into {name: value}."""
    m = re.search(r"boundary=(\S+)", content_type)
    assert m, content_type
    msg = email.message_from_bytes(
        b"Content-Type: " + content_type.encode()
        + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    out = {}
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        name = part.get_param("name", header="content-disposition")
        out[name] = part.get_payload(decode=True).decode()
    return out

class SyncComposeTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.compose_file = os.path.join(self.tmp, "docker-compose.hosted.yml")
        self.write_compose()

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

    def run_main(self, responder, extra_args=(), env=None, in_window=True,
                 endpoint=5, verify_only=False):
        """Run main() with urlopen routed by responder; returns (rc, out, err).

        Defaults to inside the AUT-5172 deploy window so the pre-existing
        cases keep testing their own subject; the gate has its own class below.
        """
        out, err = io.StringIO(), io.StringIO()
        argv = ["sync-compose-to-portainer.py",
                "--stack", "autobrain-hosted",
                "--endpoint", str(endpoint),
                "--file", self.compose_file,
                "--portainer-url", "https://portainer.example.com",
                "--api-key", "test-key"]
        if verify_only:
            argv.append("--verify-only")
        argv.extend(extra_args)
        old_argv, old_out, old_err = sys.argv, sys.stdout, sys.stderr
        sys.argv, sys.stdout, sys.stderr = argv, out, err
        try:
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    patch("urllib.request.urlopen", responder))
                stack.enter_context(patch.object(
                    scp, "in_deploy_window", lambda: in_window))
                for key, value in (env or {}).items():
                    stack.enter_context(patch.dict(
                        os.environ, {key: value}, clear=False))
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

        rc, _, _ = self.run_main(r, verify_only=True)

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
            _container("autobrain-hosted-backend-new", "backend",
                       state="created"),
        ]})
        args = _Args()

        with patch("urllib.request.urlopen", r):
            problems = scp.verify_running(args, {"backend", "frontend"},
                                          attempts=1, delay=0)

        self.assertEqual([w for _, w in problems if "stuck" in w],
                         ["stuck in state created"])

    def test_foreign_stuck_container_does_not_fail_the_gate(self):
        """AUT-5601: a foreign container wedged in `created` must not fail
        every subsequent hosted deploy.

        `fw-verify-aut5511` (AUT-5511's verify-once diagnostic) sat in
        `created` on EP5 with no compose labels and made both
        `Build hosted images (multi-arch)` runs on main red with exit 6.
        """
        r = _Responder({("GET", "/docker/containers/json"): [
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
            _container("fw-verify-aut5511", None, state="created"),
        ]})
        args = _Args()

        with patch("urllib.request.urlopen", r):
            problems = scp.verify_running(args, {"backend", "frontend"},
                                          attempts=1, delay=0)

        self.assertEqual(problems, [])


class TestDeployWindowGate(SyncComposeTestBase):
    """AUT-5172: a merge at 23:00 AEST must not redeploy the hosted stack."""

    def test_window_hours(self):
        at = lambda h, m=0: datetime(2026, 10, 2, h, m, tzinfo=scp.AEST)
        self.assertFalse(scp.in_deploy_window(at(2, 59)))
        self.assertTrue(scp.in_deploy_window(at(3, 0)))
        self.assertTrue(scp.in_deploy_window(at(3, 59)))
        self.assertFalse(scp.in_deploy_window(at(4, 0)))
        # 23:00 AEST == 13:00 UTC, the observed AUT-5172 redeploy time.
        self.assertFalse(scp.in_deploy_window(at(23, 0)))
        self.assertFalse(scp.in_deploy_window(at(13, 0)))

    def test_out_of_window_makes_no_api_call(self):
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))

        rc, out, _ = self.run_main(r, in_window=False)

        self.assertEqual(rc, 0)
        self.assertEqual(r.calls, [])
        self.assertIn("SKIP", out)
        self.assertIn("03:00-04:00 AEST", out)
        self.assertIn("left untouched", out)

    def test_override_env_permits_sync(self):
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))

        for value in ("true", "1", "YES"):
            with self.subTest(value=value):
                r.calls.clear()
                rc, _, _ = self.run_main(
                    r, env={"ALLOW_OUT_OF_WINDOW": value}, in_window=False)
                self.assertEqual(rc, 0)
                self.assertIn("PUT", r.methods_for("/api/stacks/42"))

    def test_gate_is_hosted_endpoint_only(self):
        """EP2 (9router) has no AUT-2409 window and stays hand-updatable."""
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))

        _, out, _ = self.run_main(r, in_window=False, endpoint=2)

        self.assertNotIn("SKIP", out)
        self.assertIn("PUT", r.methods_for("/api/stacks/42"))

    def test_no_override_no_put(self):
        r = _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))

        rc, _, _ = self.run_main(
            r, env={"ALLOW_OUT_OF_WINDOW": "false"}, in_window=False)

        self.assertEqual(rc, 0)
        self.assertNotIn("PUT", r.methods_for("/api/stacks/42"))

class TestNightlyHostedSync(SyncComposeTestBase):
    """AUT-5186: nightly-hosted-sync cron — in-window applies, misfire skips."""

    def _r(self):
        return _Responder(self.healthy_routes([
            _container("autobrain-hosted-backend-1", "backend"),
            _container("autobrain-hosted-frontend-1", "frontend"),
        ]))

    def test_in_window_logs_applied_digest_per_service(self):
        # The cron job sets no ALLOW_OUT_OF_WINDOW, so with the gate closed by
        # the real clock this only runs at 03:00-04:00 AEST.
        r = self._r()

        rc, out, _ = self.run_main(r, in_window=True)

        self.assertEqual(rc, 0)
        self.assertIn("PUT", r.methods_for("/api/stacks/42"))
        self.assertIn(f"applied: backend -> {BACKEND_REF}", out)
        self.assertIn(f"applied: frontend -> {FRONTEND_REF}", out)

    def test_cron_misfire_out_of_window_skips_and_logs_no_digest(self):
        # GitHub cron can fire late or early. Outside the window the run must
        # skip rather than redeploy production, and must not claim a digest.
        import os as _os
        saved = _os.environ.pop("ALLOW_OUT_OF_WINDOW", None)
        try:
            r = self._r()

            rc, out, _ = self.run_main(r, in_window=False)

            self.assertEqual(rc, 0)
            self.assertEqual(r.calls, [])
            self.assertIn("SKIP", out)
            self.assertNotIn("applied:", out)
        finally:
            if saved is not None:
                _os.environ["ALLOW_OUT_OF_WINDOW"] = saved

class TestCreateStack(SyncComposeTestBase):
    """AUT-5582: --create posts a new stack when none exists.

    The create route is a POST (not the PUT the sync path uses), the
    initial env comes only from --env-file, and the same post-deploy
    health gate + digest audit must run — a freshly created stack is
    exactly the one you cannot afford to come up broken.
    """

    MISSING_STACK_ROUTES = {
        ("GET", "/api/stacks"): [],  # no stack named autobrain-demo yet
    }

    def _env_file(self):
        path = os.path.join(self.tmp, "stack.env")
        with open(path, "w") as f:
            f.write("# comment\nPOSTGRES_USER=autobrain\n"
                    "POSTGRES_PASSWORD=hunter2\n")
        return path

    def _routes(self, containers):
        routes = dict(self.MISSING_STACK_ROUTES)
        routes[("POST", "/api/stacks/create/standalone/file")] = {
            "Id": 43, "Name": "autobrain-demo"}
        routes[("GET", "/docker/containers/json")] = containers
        routes[("GET", "/docker/containers/cid-backend/json")] = {
            "Config": {"Cmd": []}}
        routes[("GET", "/docker/images/sha256:backend")] = {
            "RepoDigests": [f"ghcr.io/x/backend@"
                            f"{BACKEND_REF.split('@', 1)[1]}"]}
        routes[("GET", "/docker/images/sha256:frontend")] = {
            "RepoDigests": [f"ghcr.io/x/frontend@"
                            f"{FRONTEND_REF.split('@', 1)[1]}"]}
        return routes

    def test_create_posts_stack_with_env_file_and_audits(self):
        r = _Responder(self._routes([
            _container("autobrain-demo-backend-1", "backend"),
            _container("autobrain-demo-frontend-1", "frontend"),
        ]))

        rc, out, _ = self.run_main(
            r, extra_args=["--create", "--env-file", self._env_file(),
                           "--stack", "autobrain-demo"])

        self.assertEqual(rc, 0)
        # Portainer 2.39 takes a multipart upload, not the JSON POST the old
        # docs show (that route is 405 behind the reverse proxy).
        self.assertEqual([u for u in r.urls("POST")],
                         ["https://portainer.example.com/api/stacks/create/"
                          "standalone/file?endpointId=5"])
        post_headers = r.headers_for("POST", "/api/stacks/create")
        ct = next(v for k, v in post_headers.items() if k.lower() == "content-type")
        fields = _multipart_fields(r.last_raw_body("POST"), ct)
        self.assertEqual(fields["Name"], "autobrain-demo")
        self.assertEqual(json.loads(fields["Env"]), [
            {"name": "POSTGRES_USER", "value": "autobrain"},
            {"name": "POSTGRES_PASSWORD", "value": "hunter2"},
        ])
        with open(self.compose_file) as f:
            self.assertIn(f.read(), fields["file"])
        self.assertIn("created", out)
        self.assertIn("id=43", out)
        self.assertIn("created", out)
        self.assertIn("verified: 2 services running", out)
        self.assertIn(f"applied: backend -> {BACKEND_REF}", out)

    def test_create_refuses_without_env_file(self):
        r = _Responder(self._routes([]))

        rc, _, err = self.run_main(
            r, extra_args=["--create", "--stack", "autobrain-demo"])

        self.assertEqual(rc, 7)
        self.assertIn("--env-file", err)
        self.assertEqual(r.methods_for("/api/stacks"), ["GET"])

    def test_create_refuses_when_orphan_holds_wanted_port(self):
        r = _Responder(self._routes([
            _container("autobrain-demo-backend-1", "backend", ports=[8000]),
            _container("autobrain-demo-frontend-1", "frontend", ports=[80]),
            _container("autobrain-ghost-1", "ghost", ports=[80]),
        ]))

        rc, _, err = self.run_main(
            r, extra_args=["--create", "--env-file", self._env_file(),
                           "--stack", "autobrain-demo"])

        self.assertEqual(rc, 5)
        self.assertIn("host port collision", err)
        self.assertEqual(r.methods_for("/api/stacks"), ["GET"])

    def test_create_reports_unhealthy_stack(self):
        r = _Responder(self._routes([
            _container("autobrain-demo-backend-1", "backend", state="created"),
        ]))

        # verify_running is patched to avoid sleeping through its 20 x 5s poll.
        with patch.object(scp, "verify_running", return_value=[
                ("/autobrain-demo-backend-1", "stuck in state created")]):
            rc, _, err = self.run_main(
                r, extra_args=["--create", "--env-file", self._env_file(),
                               "--stack", "autobrain-demo"])

        self.assertEqual(rc, 6)
        self.assertIn("is NOT healthy", err)

if __name__ == "__main__":
    unittest.main()
