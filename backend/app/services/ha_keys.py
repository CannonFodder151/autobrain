"""Home Assistant integration API keys (AUT-2541).

Same shape as `app.services.device_keys` but a distinct prefix so a leaked
HA token cannot be replayed against the device-upload surface. Tokens are
opaque, random, and stored as sha256 digests only.
"""

import hashlib
import hmac as _hmac
import secrets

PREFIX = "abha_"
PREFIX_LEN = 10


def generate_key() -> str:
    return PREFIX + secrets.token_hex(32)  # 256 bits


def key_prefix(key: str) -> str:
    return key[:PREFIX_LEN]


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_key(supplied: str, stored_hash: str) -> bool:
    return _hmac.compare_digest(hash_key(supplied), stored_hash)
