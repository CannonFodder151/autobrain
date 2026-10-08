#!/usr/bin/env python3
"""Version parity check for AutoBrain tier promotion.

Compares backend version (from /health) with frontend version (from /version.json).
Returns 0 if versions match, 1 if they differ or either is missing/unparseable.
"""
import json
import sys
import urllib.request
import urllib.error


def fetch_json(url: str, timeout: int = 10) -> dict | None:
    """Fetch and parse JSON from URL. Returns None on any error."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None


def extract_version(health_json: dict | None, version_json: dict | None) -> tuple[str | None, str | None]:
    """Extract version strings from health and version.json responses."""
    hv = health_json.get("version") if health_json else None
    vv = version_json.get("version") if version_json else None
    return hv, vv


def check_version_parity(health_url: str, timeout: int = 10, max_retries: int = 3, retry_delay: float = 2.0) -> tuple[bool, str, str]:
    """
    Check version parity between /health and /version.json.
    
    Args:
        health_url: Full URL to the tier's /health endpoint
        timeout: Per-request timeout in seconds
        max_retries: Number of retries for version.json fetch
        retry_delay: Delay between retries in seconds
    
    Returns:
        (success, health_version, version_json_version)
    """
    import time
    
    # Derive version.json URL from health URL
    if health_url.endswith("/health"):
        base = health_url[:-7]  # remove "/health"
    else:
        base = health_url.rstrip("/")
    vj_url = f"{base}/version.json"
    
    # Fetch health (assumed to have been verified by wait_health already)
    health_json = fetch_json(health_url, timeout)
    
    # Fetch version.json with retries (frontend may still be starting)
    version_json = None
    last_error = None
    for attempt in range(max_retries):
        version_json = fetch_json(vj_url, timeout)
        if version_json is not None:
            break
        last_error = f"attempt {attempt + 1}/{max_retries} failed"
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
    
    hv, vv = extract_version(health_json, version_json)
    
    if hv is None:
        return False, "", vv or ""
    if vv is None:
        return False, hv, ""
    
    return hv == vv, hv, vv


def main() -> int:
    """CLI entry point for use from bash scripts."""
    if len(sys.argv) < 2:
        print("Usage: version_parity.py <health_url> [timeout] [max_retries] [retry_delay]", file=sys.stderr)
        return 2
    
    health_url = sys.argv[1]
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    max_retries = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    retry_delay = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
    
    success, hv, vv = check_version_parity(health_url, timeout, max_retries, retry_delay)
    
    if success:
        print(f"version parity ok (backend=frontend={hv})")
        return 0
    else:
        if not hv and not vv:
            print("VERSION PARITY FAIL: could not fetch either /health or /version.json", file=sys.stderr)
        elif not hv:
            print(f"VERSION PARITY FAIL: could not parse version from /health (version.json={vv})", file=sys.stderr)
        elif not vv:
            print(f"VERSION PARITY FAIL: /version.json not served or unparseable (health={hv})", file=sys.stderr)
        else:
            print(f"VERSION PARITY FAIL: /health={hv} but /version.json={vv} — frontend bundle stale vs backend image", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
