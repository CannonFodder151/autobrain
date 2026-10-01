#!/usr/bin/env python3
"""Regression test for the docs.json page map consumed by sync-docs-outline.mjs.

Every page ref in docs/docs.json must resolve to docs/<ref>.md, so a rename in
docs/ cannot silently orphan the map and fail the docs-sync workflow.
"""
import json
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_JSON = os.path.join(REPO, "docs", "docs.json")


def page_refs():
    with open(DOCS_JSON) as f:
        config = json.load(f)
    refs = []
    for tab in config.get("navigation", {}).get("tabs", []):
        for group in tab.get("groups", []):
            refs.extend(group.get("pages", []))
    return refs


class TestDocsJsonPageMap(unittest.TestCase):

    def test_docs_json_is_valid_json(self):
        self.assertGreater(len(page_refs()), 0)

    def test_every_page_ref_resolves_to_a_file(self):
        missing = [r for r in page_refs() if not os.path.isfile(os.path.join(REPO, "docs", r + ".md"))]
        self.assertEqual(missing, [], "docs.json page refs with no matching markdown file")


if __name__ == "__main__":
    unittest.main()
