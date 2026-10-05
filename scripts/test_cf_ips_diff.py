#!/usr/bin/env python3
"""AUT-5695: regression tests for scripts/cf-ips-diff.sh (the Cloudflare
`set_real_ip_from` drift guard).

Three guards:
1. the real frontend configs pass against the LIVE Cloudflare ranges (exit 0);
   this is the regression that caught the 198.41.128.0/17 drift on main.
2. a config missing a live range fails (exit 1) — the drift must fail loudly,
   not silently re-open the AUT-3858/AUT-5460 login lockout.
3. a config with an extra (stale/hand-typed) range also fails (exit 1).

Skipped when Cloudflare's public endpoints are unreachable (e.g. offline CI
without egress) — the CI job itself runs the script directly and is the
authoritative gate; this module is the fast, network-gated regression.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "cf-ips-diff.sh")

# A complete, live-shaped list — used to build a "stale" config for guard 2.
# (The real confs are the source of truth; this is just a known-good subset
# used to seed the negative test without depending on the network at import
# time.)
KNOWN_RANGE = "173.245.48.0/20"


def _has_egress() -> bool:
    # Match the script's own transport (curl) — urllib's TLS stack may
    # reject the cert in some sandboxes where curl succeeds.
    return (
        shutil.which("curl") is not None
        and subprocess.run(
            ["curl", "-fsS", "--max-time", "8", "https://www.cloudflare.com/ips-v4"],
            capture_output=True,
        ).returncode
        == 0
    )


@unittest.skipUnless(_has_egress(), "no egress to cloudflare.com/ips-v4")
class TestCfIpsDiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(SCRIPT):
            raise unittest.SkipTest(f"{SCRIPT} not found")

    def _run(self, confs, env_extra=None):
        env = dict(os.environ)
        env["CF_IPS_CONFS"] = " ".join(confs)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["bash", SCRIPT], cwd=REPO, capture_output=True, text=True, env=env
        )

    def test_real_configs_match_live_ranges(self):
        r = self._run(
            [
                "docker/frontend/nginx.conf",
                "docker/frontend/nginx-proxy.conf",
            ]
        )
        self.assertEqual(
            r.returncode,
            0,
            f"drift guard should pass on the real confs (stdout={r.stdout}\nstderr={r.stderr})",
        )
        self.assertIn("OK:", r.stdout)

    def test_missing_range_fails(self):
        """The exact regression AUT-5695 caught: a dropped range must fail."""
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "nginx.conf")
            # Copy the real conf and strip one known-live range.
            real = os.path.join(
                REPO, "docker", "frontend", "nginx.conf"
            )
            with open(real) as f:
                text = f.read()
            text = text.replace(
                "set_real_ip_from 198.41.128.0/17;", "# set_real_ip_from 198.41.128.0/17;"
            )
            with open(conf, "w") as f:
                f.write(text)
            r = self._run([conf])
            self.assertEqual(
                r.returncode,
                1,
                f"missing range must fail (stdout={r.stdout}\nstderr={r.stderr})",
            )
            self.assertIn("MISSING", r.stderr)

    def test_extra_range_fails(self):
        """A stale/hand-typed range beyond the live set must also fail."""
        with tempfile.TemporaryDirectory() as d:
            conf = os.path.join(d, "nginx.conf")
            real = os.path.join(
                REPO, "docker", "frontend", "nginx.conf"
            )
            with open(real) as f:
                text = f.read()
            # Append a bogus range that Cloudflare never published.
            text += "\n    set_real_ip_from 203.0.113.0/24;\n"
            with open(conf, "w") as f:
                f.write(text)
            r = self._run([conf])
            self.assertEqual(
                r.returncode,
                1,
                f"extra range must fail (stdout={r.stdout}\nstderr={r.stderr})",
            )
            self.assertIn("EXTRA", r.stderr)


if __name__ == "__main__":
    unittest.main()