"""Admin API v1 subpackage.

Exports two routers matching the original admin.py interface:
- ``router``: user management at ``/admin/users``
- ``admin_ops``: server ops, social config, and moderation at ``/admin``
"""

from fastapi import APIRouter

from app.api.v1.admin.users import router as users_router
from app.api.v1.admin.server_ops import router as server_ops_router
from app.api.v1.admin.social import router as social_router
from app.api.v1.admin.moderation import router as moderation_router

# User management router (prefix /admin/users)
router = users_router

# Combined admin operations router (prefix /admin)
# Includes server ops, social config, and moderation endpoints
admin_ops = APIRouter(prefix="/admin", tags=["admin"])
admin_ops.include_router(server_ops_router)
admin_ops.include_router(social_router)
admin_ops.include_router(moderation_router)