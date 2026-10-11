"""Social Issues Blog — schemas and constants."""

from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.social.models import SocialIssuePost


ISSUE_STATUSES = {"open", "answered", "resolved"}

MAX_TITLE = 150
MAX_BODY = 4000
MAX_COMMENT = 2000
MAX_REASON = 200
MAX_PHOTOS = 4
_LIST_LIMIT_MAX = 50


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    body: str = Field(min_length=1, max_length=MAX_BODY)
    vehicle_id: str | None = Field(default=None, max_length=36)
    photo_ids: list[str] = Field(default_factory=list, max_length=MAX_PHOTOS)


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    body: str | None = Field(default=None, min_length=1, max_length=MAX_BODY)
    status: str | None = Field(default=None)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_COMMENT)
    photo_id: str | None = Field(default=None, max_length=36)


class FlagIn(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_REASON)


def _plaintext(value: str) -> str:
    """Strip control characters so bodies are render-safe plaintext (no XSS).

    Only newlines survive; tabs/other C0 controls become spaces.
    """
    return "".join(
        ch if ch.isprintable() else ("\n" if ch == "\n" else " ")
        for ch in value
    )


def _vehicle_snapshot(vehicle) -> dict:
    return {k: getattr(vehicle, k) for k in ("make", "model", "year") if getattr(vehicle, k)}


def _parse_remote_created(value: str | None) -> datetime:
    """Parse an origin's ISO created_at, tolerating a trailing Z."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _encode_cursor(created_at, post_id: str) -> str:
    import base64
    import json

    raw = json.dumps({"c": created_at.isoformat(), "i": post_id}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str):
    import base64
    import json
    from datetime import datetime
    from fastapi import HTTPException

    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(raw["c"]), str(raw["i"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid cursor")


def _tags_contains(db, tag: str):
    """Portable tag filter: native array containment on postgres, JSON-text
    LIKE elsewhere (sqlite test engines). `tag` is vocab-validated upstream.
    Cast to plain Text so the TypeDecorator's JSON bind processing never
    applies to the LIKE pattern."""
    from sqlalchemy import Text, text, cast

    if db.get_bind().dialect.name == "postgresql":
        return text(":t = ANY(social_issue_posts.tags)").bindparams(t=tag)
    return cast(SocialIssuePost.tags, Text).like(f'%"{tag}"%')