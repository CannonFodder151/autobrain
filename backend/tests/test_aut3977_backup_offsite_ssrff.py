"""AUT-3977: BACKUP_OFFSITE_URL SSRF guard — fail closed on unauthorised hosts.

Regression test: must FAIL against the pre-fix code (no validator) and PASS
against the fix. The validator lives in `app.core.config` and is wired into
`Settings` via a model validator, so any non-empty `BACKUP_OFFSITE_URL` that
does not resolve to an authorised host must raise a ValidationError at startup.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# Minimal env so Settings() itself does not fail on unrelated required fields.
_BASE_ENV = {
    "ENVIRONMENT": "dev",
    "POSTGRES_USER": "u",
    "POSTGRES_PASSWORD": "p",
    "MINIO_ACCESS_KEY": "a",
    "MINIO_SECRET_KEY": "s",
    "SECRET_KEY": "x",
}


def _settings(**env) -> Settings:
    return Settings(_env_file=None, **env)


# --- Invalid: must be rejected ----------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata (SSRF)
        "http://169.254.169.254/",                  # metadata base
        "http://localhost:9000",                    # loopback alias
        "http://127.0.0.1:9000",                    # loopback IPv4
        "http://[::1]/",                            # loopback IPv6
        "http://ip6-localhost/",                    # loopback alias
        "http://evil.com/exfil",                    # public DNS
        "http://attacker-autobrain-backupx.evil.com/",  # prefix-spoof
        "http://postgres:5432",                     # internal service name
        "http://redis:6379",                        # internal service name
        "ftp://autobrain-backup/",                  # wrong scheme
        "gopher://autobrain-backup/",               # wrong scheme
        "http://10.0.0.5/b",                        # RFC1918 literal, not allowlisted
        "http://192.168.1.1/b",                     # RFC1918 literal, not allowlisted
        "http://8.8.8.8/",                          # public IP literal
        # Prefix/suffix bypasses. The guard matches the whole host exactly, so
        # an attacker who registers a domain cannot satisfy it by embedding
        # "autobrain-backup" in one label.
        "http://autobrain-backup.evil.com/",        # prefix as leftmost label
        "http://autobrain-backup.attacker.net/",    # attacker-registered domain
        "http://autobrain-backup-evil.com/",        # dash form
        "http://autobrain-backup.example.evil.com/",  # prefix + hostile parent
        "http://autobrain-backup./",                # trailing-dot FQDN
        "http://AUTOBRAIN-BACKUP.EVIL.COM/",        # case-folded prefix spoof
        "http://autobrain-backup@evil.com/",        # userinfo prefix spoof
        "http://2852039166/",                       # decimal-encoded metadata
        "http://0x7f.0.0.1/",                       # hex-encoded loopback
        "http://[::ffff:169.254.169.254]/",         # IPv4-mapped metadata
        # The docker-compose default is NOT implicitly authorised: without an
        # allowlist entry it must fail closed rather than boot.
        "http://backup:8080",
    ],
)
def test_invalid_offsite_url_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        _settings(BACKUP_OFFSITE_URL=url)


def test_compose_default_host_requires_allowlist_entry() -> None:
    """docker-compose.hosted.yml ships this host in the allowlist explicitly.

    Guards the deploy-time wiring: the default must keep working *because* the
    allowlist names it, not because the validator lets the name through.
    """
    s = _settings(
        BACKUP_OFFSITE_URL="http://backup:8080",
        BACKUP_OFFSITE_HOST_ALLOWLIST=["backup"],
    )
    assert s.BACKUP_OFFSITE_URL == "http://backup:8080"


def test_trailing_dot_host_matches_allowlist_entry() -> None:
    """`autobrain-backup.` is the same host as `autobrain-backup`."""
    s = _settings(
        BACKUP_OFFSITE_URL="http://autobrain-backup./",
        BACKUP_OFFSITE_HOST_ALLOWLIST=["autobrain-backup"],
    )
    assert s.BACKUP_OFFSITE_URL == "http://autobrain-backup./"


def test_localhost_via_allowlist_still_rejected() -> None:
    """Allowlist entries cannot override the loopback/link-local block."""
    with pytest.raises(ValidationError):
        _settings(
            BACKUP_OFFSITE_URL="http://127.0.0.1:9000",
            BACKUP_OFFSITE_HOST_ALLOWLIST=["127.0.0.1"],
        )


def test_metadata_ip_via_allowlist_still_rejected() -> None:
    """Allowlist entries cannot override the link-local (metadata) block."""
    with pytest.raises(ValidationError):
        _settings(
            BACKUP_OFFSITE_URL="http://169.254.169.254/latest/meta-data/",
            BACKUP_OFFSITE_HOST_ALLOWLIST=["169.254.169.254"],
        )


# --- Valid: must pass -------------------------------------------------------

@pytest.mark.parametrize(
    "url,host",
    [
        ("https://autobrain-backup.example.internal/backups", "autobrain-backup.example.internal"),
        ("https://autobrain-backup-primary.example.internal:9000/b", "autobrain-backup-primary.example.internal"),
        ("https://autobrain-backup-2.example.internal/x", "autobrain-backup-2.example.internal"),
        ("https://autobrain-backup/", "autobrain-backup"),
    ],
)
def test_valid_offsite_url_accepted(url: str, host: str) -> None:
    s = _settings(BACKUP_OFFSITE_URL=url, BACKUP_OFFSITE_HOST_ALLOWLIST=[host])
    assert s.BACKUP_OFFSITE_URL == url


def test_allowlisted_rfc1918_accepted() -> None:
    s = _settings(
        BACKUP_OFFSITE_URL="http://10.0.0.5/backups",
        BACKUP_OFFSITE_HOST_ALLOWLIST=["10.0.0.5"],
    )
    assert s.BACKUP_OFFSITE_URL == "http://10.0.0.5/backups"


def test_empty_url_means_disabled() -> None:
    """An empty BACKUP_OFFSITE_URL is "disabled" and must not raise."""
    s = _settings(BACKUP_OFFSITE_URL="")
    assert s.BACKUP_OFFSITE_URL == ""