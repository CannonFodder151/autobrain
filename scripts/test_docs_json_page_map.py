#!/usr/bin/env python3
"""Regression test for the docs.json page map consumed by sync-docs-outline.mjs.

Every page ref in docs/docs.json must resolve to docs/<ref>.md, so a rename in
docs/ cannot silently orphan the map and fail the docs-sync workflow.

AUT-4883 extensions:
- Recursively walks nested group structures (not just flat groups)
- Optional reverse check: .md files in docs/ not referenced in the map
- Optional hard gate via environment variable DOCS_PAGE_MAP_HARD_GATE=1
"""
import json
import os
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DOCS_JSON = REPO / "docs" / "docs.json"
DOCS_DIR = REPO / "docs"

HARD_GATE = os.getenv("DOCS_PAGE_MAP_HARD_GATE") == "1"
CHECK_ORPHANS = os.getenv("DOCS_PAGE_MAP_CHECK_ORPHANS") == "1"


def _walk_pages(node, refs):
    """Recursively extract page refs from navigation structure."""
    if isinstance(node, dict):
        # Check for pages list
        if "pages" in node and isinstance(node["pages"], list):
            refs.extend(node["pages"])
        # Recurse into all dict values
        for v in node.values():
            _walk_pages(v, refs)
    elif isinstance(node, list):
        for item in node:
            _walk_pages(item, refs)


def page_refs():
    with open(DOCS_JSON) as f:
        config = json.load(f)
    refs = []
    _walk_pages(config.get("navigation", {}), refs)
    return refs


def all_md_files():
    """Return all .md files under docs/ as relative paths without extension."""
    md_files = []
    for md_file in DOCS_DIR.rglob("*.md"):
        rel = md_file.relative_to(DOCS_DIR)
        # Remove .md extension
        md_files.append(str(rel.with_suffix("")))
    return md_files


class TestDocsJsonPageMap(unittest.TestCase):

    def test_docs_json_is_valid_json(self):
        refs = page_refs()
        self.assertGreater(len(refs), 0, "No page refs found in docs.json")

    def test_every_page_ref_resolves_to_a_file(self):
        missing = [r for r in page_refs() if not (DOCS_DIR / (r + ".md")).is_file()]
        self.assertEqual(
            missing,
            [],
            f"docs.json page refs with no matching markdown file: {missing}",
        )

    def test_no_orphan_md_files(self):
        """Reverse check: every .md file in docs/ must be referenced in docs.json.

        This check is opt-in (DOCS_PAGE_MAP_CHECK_ORPHANS=1) and report-only
        by default. Set DOCS_PAGE_MAP_ORPHAN_HARD_FAIL=1 to make it fail.

        Exclusions can be configured via DOCS_PAGE_MAP_ORPHAN_EXCLUDE (comma-separated
        path prefixes or exact paths).
        """
        if not CHECK_ORPHANS:
            self.skipTest("Set DOCS_PAGE_MAP_CHECK_ORPHANS=1 to enable orphan check")
        refs = set(page_refs())
        md_files = set(all_md_files())

        # Default exclusions: files intentionally not in the navigation map
        default_excludes = {
            "README",
            "CHANGELOG",
            "LICENSE",
            "desktop-breakpoints-audit-AUT-2524",
            "home-assistant-integration",
            "petrol-price-map",
        }
        # Additional exclusions from env var
        env_excludes = os.getenv("DOCS_PAGE_MAP_ORPHAN_EXCLUDE", "")
        if env_excludes:
            default_excludes.update(e.strip() for e in env_excludes.split(",") if e.strip())

        orphans = sorted(
            f for f in md_files - refs
            if f not in default_excludes
            and not any(f.startswith(p + "/") for p in default_excludes if "/" in p)
        )

        if orphans:
            msg = f"Orphan .md files not referenced in docs.json: {orphans}"
            if os.getenv("DOCS_PAGE_MAP_ORPHAN_HARD_FAIL") == "1":
                self.fail(msg)
            else:
                print(f"WARNING: {msg}")


if __name__ == "__main__":
    # Run with hard gate: exit non-zero on any failure
    if HARD_GATE:
        os.environ["DOCS_PAGE_MAP_HARD_GATE"] = "1"
    unittest.main(exit=HARD_GATE)