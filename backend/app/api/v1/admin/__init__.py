"""Admin API v1 subpackage.

Splits the former `app/api/v1/admin.py` monolith into a subpackage with
separate modules per concern:
  - users.py    — user CRUD routes (`router`, prefix /admin/users)
  - ops.py      — server ops + moderation routes (`admin_ops`, prefix /admin)
  - helpers.py  — shared utilities (_escape_ilike, _best_effort_delete_media)
  - schemas.py  — local Pydantic request models

Backwards-compatibility re-exports so `app.api.v1` can keep importing
`admin.router` / `admin.admin_ops` unchanged.
"""

from app.api.v1.admin.helpers import _best_effort_delete_media, _escape_ilike
from app.api.v1.admin.ops import admin_ops
from app.api.v1.admin.schemas import _IssueModerationUpdate, _SocialConfigUpdate
from app.api.v1.admin.users import router

__all__ = [
    "router",
    "admin_ops",
    "_escape_ilike",
    "_best_effort_delete_media",
    "_SocialConfigUpdate",
    "_IssueModerationUpdate",
]