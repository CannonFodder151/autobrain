"""AUT-1167: smoke/deploy test recipients are suppressed so dead addresses
never hit the SMTP relay (SMTP2GO complaint: bounces from test sends)."""

import pytest

from app.services.email import _is_suppressed


@pytest.fixture(autouse=True)
def _reset_suppression_cache():
    """Settings are process-cached; ensure the module cache is fresh."""
    from app.services import email

    email._suppress_domain_set = None
    email._suppress_pattern_re = None
    yield
    email._suppress_domain_set = None
    email._suppress_pattern_re = None


DEAD_ADDRESSES = [
    "aut507-host@testmail.com",
    "aut576-check@autobrainservice.app",
    "aut674-test-9382@example.com",
    "deploy-aut604@autobrainservice.app",
    "deploy.aut765.hosted.1786771147@gmail.com",
    "deploytest-1786714030@example.com",
    "deploytest-1786714075@example.com",
    "deploytest-1786714104@example.com",
    "deploytest-1786714130@example.com",
    "deploy-test-aut682-hosted@autobrainservice.app",
    "qa.license.verify@example.com",
    "qa.verify.aut632@example.com",
    "smoke-aut757-1786765465@example.com",
    "smoke-aut757-1786765494@example.com",
    "smoke-aut757-1786765868@example.com",
    "smoke-aut757-eddrng@example.com",
    "smoke-aut757-fdvkak@example.com",
    "smoke-aut757-iclcjk@example.com",
    "smoke-aut757-pyhftd@example.com",
    "smoke-aut757-xxcrqq@example.com",
    "smoke-aut757-ybimvo@example.com",
    "smokehst2@autobrainservice.app",
    "smoke-t-1@example.com",
]

REAL_ADDRESSES = [
    "nathan@example-real.com",
    "jane@autobrainservice.app",
    "bob@testloop.com",
    "smokey@gmx.com",
    "deployment@company.com",
    "user+smoke@realmail.com",
    "someone@gmail.com",
]


@pytest.mark.parametrize("addr", DEAD_ADDRESSES)
def test_dead_test_addresses_suppressed(addr):
    assert _is_suppressed(addr), f"{addr} must be suppressed"


@pytest.mark.parametrize("addr", REAL_ADDRESSES)
def test_real_addresses_not_suppressed(addr):
    assert not _is_suppressed(addr), f"{addr} must be delivered"


def test_case_insensitive_domain():
    assert _is_suppressed("Smoke-1@Example.COM")