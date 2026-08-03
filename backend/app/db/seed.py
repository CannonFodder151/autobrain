"""Seed utilities: creates the bootstrap admin account from env vars."""

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User

logger = get_logger(__name__)


async def seed_admin() -> None:
    """Ensure the admin account from ADMIN_EMAIL/ADMIN_INITIAL_PASSWORD exists."""
    email = (settings.ADMIN_EMAIL or "").strip().lower()
    password = (settings.ADMIN_INITIAL_PASSWORD or "").strip()
    if not email or not password:
        logger.info("admin_seed_skipped_no_config")
        return
    async with SessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing:
            logger.info("admin_seed_already_exists", email=email)
            return
        db.add(
            User(
                email=email,
                display_name=settings.ADMIN_DISPLAY_NAME,
                hashed_password=hash_password(password),
                role="admin",
            )
        )
        await db.commit()
        logger.info("admin_seed_created", email=email)
