#!/usr/bin/env python3
"""Guard: the default promotion chain still covers Demo, Default and Hosted.

AUT-4982 — AUT-2409 narrowed DEFAULT_TIERS in scripts/upgrade-instances.sh to
Hosted-only. Nothing redeployed the EP2 stacks afterwards, so demo
(demo.autobrainservice.app) went 502 and stayed down. This test fails if the
chain is narrowed again, or if a tier loses its health URL (a tier with no
health check is silently promoted through).
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "upgrade-instances.sh")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "deploy-instances.yml")

# name, Portainer endpoint id, health URL path — the board-mandated order (AUT-107).
EXPECTED_CHAIN = [
    ("autobrain-demo", "2", "https://demo.autobrainservice.app/health"),
    ("autobrain", "2", "https://default.autobrainservice.app/health"),
    ("autobrain-hosted", "5", "https://hosted.autobrainservice.app/health"),
]


def _default_tiers(script: str):
    """Parse DEFAULT_TIERS out of the shell script into (name, endpoint, health)."""
    block = re.search(r"^DEFAULT_TIERS=\"$(.*?)^\"$", script, re.S | re.M)
    assert block, "DEFAULT_TIERS assignment not found in upgrade-instances.sh"
    tiers = []
    for line in block.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, endpoint, health, _required_env = line.split("|", 3)
        tiers.append((name, endpoint, health))
    return tiers


class TestUpgradeInstanceTiers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(SCRIPT) as f:
            cls.script = f.read()
        with open(WORKFLOW) as f:
            cls.workflow = f.read()
        cls.tiers = _default_tiers(cls.script)

    def test_default_chain_is_demo_default_hosted_in_promotion_order(self):
        self.assertEqual(self.tiers, EXPECTED_CHAIN)

    def test_every_default_tier_has_a_health_url(self):
        # An empty health URL means wait_health "" never succeeds, so the tier
        # would be marked UNHEALTHY and abort the rollout.
        for name, _endpoint, health in self.tiers:
            with self.subTest(tier=name):
                self.assertTrue(health.startswith("https://"), f"{name} has no health URL")

    def test_workflow_exposes_tiers_override(self):
        # The `tiers` input is what lets a dispatch honour the hosted
        # 03:00-04:00 AEST window (AUT-2409 / AUT-5172) without re-narrowing
        # the defaults again.
        self.assertIn("tiers:", self.workflow)
        self.assertIn("UPGRADE_TIERS: ${{ inputs.tiers }}", self.workflow)

    def test_tiers_input_still_falls_back_to_the_full_chain(self):
        # TIERS="${UPGRADE_TIERS:-$DEFAULT_TIERS}" — a blank dispatch input must
        # NOT collapse the chain to nothing.
        self.assertIn('TIERS="${UPGRADE_TIERS:-$DEFAULT_TIERS}"', self.script)


if __name__ == "__main__":
    unittest.main()
