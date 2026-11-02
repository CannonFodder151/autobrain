#!/usr/bin/env python3
"""Guard: the pipeline-stages workflow enforces demo -> default -> hosted with
per-tier health gates.

AUT-180 — Configure GitHub Actions pipeline stages for demo, default, and
hosted environments with test gates.

The promotion order is load-bearing (AUT-107): a tier that fails health must
block promotion to the next tier. This test fails if a stage is reordered, a
stage loses its health gate, or a stage drops its Portainer endpoint.
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "pipeline-stages.yml")

# Stage name, Portainer endpoint id, health URL — the board-mandated order.
EXPECTED_STAGES = [
    ("stage-demo", "2", "https://demo.autobrainservice.app/health"),
    ("stage-default", "2", "https://default.autobrainservice.app/health"),
    ("stage-hosted", "5", "https://hosted.autobrainservice.app/health"),
]


class TestPipelineStages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW) as f:
            cls.workflow = f.read()

    def _stage_block(self, name):
        """Return the text of a single job block, up to the next top-level job."""
        marker = f"  {name}:"
        start = self.workflow.find(marker)
        self.assertGreaterEqual(start, 0, f"stage {name} missing from workflow")
        rest = self.workflow[start:]
        end = len(rest)
        for n2, _e2, _h2 in EXPECTED_STAGES:
            j = rest.find(f"\n  {n2}:\n")
            if j > 0:
                end = min(end, j)
        return rest[:end]

    def test_workflow_exists_and_parses(self):
        import yaml
        doc = yaml.safe_load(self.workflow)
        self.assertIsInstance(doc, dict)
        self.assertIn("name", doc)
        self.assertIn("jobs", doc)

    def test_stages_are_in_promotion_order(self):
        idx = -1
        for name, _ep, _health in EXPECTED_STAGES:
            i = self.workflow.find(f"  {name}:")
            self.assertGreaterEqual(i, 0, f"stage {name} missing")
            self.assertGreater(i, idx, f"stage {name} out of order")
            idx = i

    def test_every_stage_has_a_health_gate(self):
        for name, _ep, health in EXPECTED_STAGES:
            with self.subTest(stage=name):
                block = self._stage_block(name)
                self.assertIn(health, block, f"{name} health URL missing")
                self.assertIn("health gate", block.lower(),
                              f"{name} missing a health-gate step")

    def test_every_stage_uses_correct_portainer_endpoint(self):
        for name, ep, _health in EXPECTED_STAGES:
            with self.subTest(stage=name):
                block = self._stage_block(name)
                self.assertIn(f"|{ep}|", block,
                              f"{name} uses wrong Portainer endpoint {ep}")

    def test_stages_depend_on_each_other(self):
        pairs = list(zip(EXPECTED_STAGES, EXPECTED_STAGES[1:]))
        for (n1, _e1, _h1), (n2, _e2, _h2) in pairs:
            with self.subTest(stage=n2):
                block = self._stage_block(n2)
                self.assertIn(f"needs: {n1}", block,
                              f"{n2} does not depend on {n1}")


if __name__ == "__main__":
    unittest.main()