from fastapi import APIRouter

from app.api.v1.admin.users import router as users_router
from app.api.v1.admin.analytics import router as analytics_router
from app.api.v1.admin.config import router as config_router
from app.api.v1.admin.backup import router as backup_router

router = APIRouter(prefix="/admin")
router.include_router(users_router)
router.include_router(analytics_router)
router.include_router(config_router)
router.include_router(backup_router)
