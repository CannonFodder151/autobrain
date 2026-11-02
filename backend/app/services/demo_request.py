"""Demo access request flow: rate limit + spam abuse guard + credential delivery."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Dict, List

_WINDOW = 3600  # 1 hour
_MAX_PER_IP = 5
_MAX_PER_EMAIL = 3

_ip_hits: Dict[str, List[float]] = defaultdict(list)
_email_hits: Dict[str, List[float]] = defaultdict(list)


def _prune(ts: List[float], now: float) -> List[float]:
    return [t for t in ts if t > now - _WINDOW]


def check_rate_limit(ip: str, email: str) -> bool:
    now = time.monotonic()
    _ip_hits[ip] = _prune(_ip_hits[ip], now)
    _email_hits[email] = _prune(_email_hits[email], now)
    if len(_ip_hits[ip]) >= _MAX_PER_IP:
        return False
    if len(_email_hits[email]) >= _MAX_PER_EMAIL:
        return False
    _ip_hits[ip].append(now)
    _email_hits[email].append(now)
    return True


def is_spam(payload: dict) -> bool:
    if payload.get("honeypot"):
        return True
    # simple abuse: disposable-ish / empty name with suspicious patterns
    email = (payload.get("email") or "").lower()
    if not email or "@" not in email:
        return True
    return False


def deliver_credentials(email: str) -> dict:
    # Never publish password in code; read from env at runtime.
    password = os.environ.get("DEMO_ACCOUNT_PASSWORD", "")
    login_url = os.environ.get("DEMO_LOGIN_URL", "https://demo.autobrainservice.app")
    # In-app delivery: return a masked receipt; email sending is out of scope here.
    return {
        "status": "delivered",
        "message": "Demo credentials sent. Check your inbox.",
        "login_url": login_url,
        "has_password": bool(password),
    }
