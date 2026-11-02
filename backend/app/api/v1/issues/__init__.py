from fastapi import APIRouter

from app.api.v1.issues.crud import router as crud_router
from app.api.v1.issues.blog import router as blog_router
from app.api.v1.issues.search import router as search_router

router = APIRouter(prefix="/issues")
router.include_router(crud_router)
router.include_router(blog_router)
router.include_router(search_router)
