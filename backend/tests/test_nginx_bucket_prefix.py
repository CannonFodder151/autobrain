#!/usr/bin/env python3
"""Self-check for AUT-4317 nginx bucket prefix regex location.

Validates that the nginx regex location correctly matches the expected
bucket prefixes used across environments.
"""
import re
from pathlib import Path

NGINX_CONF = Path(__file__).parents[2] / "docker" / "frontend" / "nginx.conf"


def test_nginx_regex_in_config():
    """The nginx.conf should contain the regex location for both prefixes."""
    content = NGINX_CONF.read_text()
    assert "autobrain-assets" in content
    assert "autobrainservice-assets" in content
    assert "location ~ ^/(autobrain-assets|autobrainservice-assets)/" in content


def test_nginx_regex_matches_expected_prefixes():
    """Both environment bucket prefixes should match."""
    bucket_regex = re.compile(r'^/(autobrain-assets|autobrainservice-assets)/')
    assert bucket_regex.match('/autobrain-assets/demo/x.png') is not None
    assert bucket_regex.match('/autobrainservice-assets/demo/x.png') is not None


def test_nginx_regex_does_not_match_unrelated():
    """Unrelated paths should not match the bucket prefix location."""
    bucket_regex = re.compile(r'^/(autobrain-assets|autobrainservice-assets)/')
    assert bucket_regex.match('/api/v1/social/issues') is None
    assert bucket_regex.match('/assets/foo.png') is None
    assert bucket_regex.match('/health') is None


def test_nginx_regex_matches_query_strings():
    """Presigned URLs with query strings should match."""
    bucket_regex = re.compile(r'^/(autobrain-assets|autobrainservice-assets)/')
    assert bucket_regex.match('/autobrainservice-assets/demo/x.png?X-Amz-Signature=abc') is not None


if __name__ == "__main__":
    test_nginx_regex_in_config()
    test_nginx_regex_matches_expected_prefixes()
    test_nginx_regex_does_not_match_unrelated()
    test_nginx_regex_matches_query_strings()
    print("✓ All AUT-4317 nginx bucket prefix self-checks passed")

