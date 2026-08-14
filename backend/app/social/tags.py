"""Deterministic issue auto-tags from a fixed vocabulary (AUT-627). No AI.

AI tag refinement is deliberately NOT in this path — the deterministic set is
authoritative. Add an AI pass only if a future requirement needs it, and merge
it against this set (never replacing it).
"""

# Fixed vocabulary, all lowercase. Substring-matched against the plaintext.
TAG_VOCABULARY = [
    "engine",
    "brakes",
    "electrical",
    "interior",
    "suspension",
    "transmission",
    "cooling",
    "exhaust",
    "fuel",
    "steering",
    "battery",
    "starting",
    "overheating",
    "tyres",
    "body",
    "clutch",
    "oil",
    "noise",
    "vibration",
    "warning",
]

# High-precision synonyms that resolve to a vocabulary tag (avoids e.g. a post
# that says "gear stick" never getting a tag).
_ALIASES = {
    "gearbox": "transmission",
    "radiator": "cooling",
    "coolant": "cooling",
    "alternator": "electrical",
    "starter motor": "starting",
}


def detect_tags(title: str, body: str, vehicle: dict | None = None) -> list[str]:
    """Match the fixed vocabulary against title + body + vehicle context.

    `vehicle` is a snapshot dict (make/model/year). Deterministic, ordered,
    deduplicated. Returns an empty list when nothing matches.
    """
    parts = [title or "", body or ""]
    if vehicle:
        for key in ("make", "model", "year"):
            value = vehicle.get(key)
            if value:
                parts.append(str(value))
    text = " ".join(parts).lower()

    matched: set[str] = set()
    for term in TAG_VOCABULARY:
        if term in text:
            matched.add(term)
    for alias, tag in _ALIASES.items():
        if alias in text:
            matched.add(tag)

    return [t for t in TAG_VOCABULARY if t in matched]
