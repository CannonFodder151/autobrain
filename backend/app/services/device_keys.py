"""Dongle device API keys — deterministic, no AI (AUT-918).

Keys are opaque 256-bit random strings the dongle presents as
`X-Device-API-Key`. The backend stores only a sha256 digest, so a DB leak
cannot be replayed as a live key. Lookup narrows to a short prefix index
before the full digest is compared in constant time.
"""

import hashlib
import hmac as _hmac
import secrets

# Prefix so keys are greppable/recognisable in logs and never mistaken for a
# JWT or the admin key.
PREFIX = "abdev_"

# Indexed prefix length: PREFIX + 4 hex chars of randomness (narrower than the
# full key, unique enough to drive the index without leaking the key).
PREFIX_LEN = 10


def generate_key() -> str:
    """Return a fresh opaque device API key, e.g. `abdev_<64 hex chars>`."""
    return PREFIX + secrets.token_hex(32)  # 256 bits


def key_prefix(key: str) -> str:
    return key[:PREFIX_LEN]


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_key(supplied: str, stored_hash: str) -> bool:
    """Constant-time comparison of the supplied key against a stored digest."""
    return _hmac.compare_digest(hash_key(supplied), stored_hash)