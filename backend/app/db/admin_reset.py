"""Admin password reset CLI.

Run inside the backend container to rotate the super-admin password.

Usage:
    python -m app.db.admin_reset

Environment:
    ADMIN_EMAIL            Email of the admin account to reset (required)
    ADMIN_NEW_PASSWORD     New password (plaintext). Mutually exclusive with ADMIN_NEW_PASSWORD_FILE.
    ADMIN_NEW_PASSWORD_FILE  Path to file containing the new password (secret-file pattern).

The script reads settings from the same config as the backend (env + secret files).
On success it prints a JSON summary with the admin user id and email.
The new password is NEVER logged.
"""

import asyncio
import json
import os
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User

logger = get_logger(__name__)


async def reset_admin_password() -> dict:
    email = (settings.ADMIN_EMAIL or "").strip().lower()
    if not email:
        raise RuntimeError("ADMIN_EMAIL is not set")

    # Resolve new password from env or secret file
    new_password = (os.getenv("ADMIN_NEW_PASSWORD") or "").strip()
    password_file = os.getenv("ADMIN_NEW_PASSWORD_FILE", "").strip()
    if not new_password and password_file:
        try:
            with open(password_file, "r", encoding="utf-8") as f:
                new_password = f.read().strip()
        except OSError as exc:
            raise RuntimeError(f"Failed to read ADMIN_NEW_PASSWORD_FILE: {exc}") from exc

    if not new_password:
        raise RuntimeError("ADMIN_NEW_PASSWORD or ADMIN_NEW_PASSWORD_FILE must be set")

    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if not user:
            raise RuntimeError(f"Admin user not found: {email}")

        user.hashed_password = hash_password(new_password)
        user.token_version += 1  # revoke all outstanding sessions
        await db.commit()
        await db.refresh(user)

        logger.info("admin_password_reset", user_id=user.id, email=user.email)
        return {"user_id": user.id, "email": user.email, "status": "reset"}


def main() -> None:
    try:
        result = asyncio.run(reset_admin_password())
        print(json.dumps(result))
    except Exception as exc:  # noqa: BLE001 — CLI must surface all errors
        logger.error("admin_password_reset_failed", error=str(exc))
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()