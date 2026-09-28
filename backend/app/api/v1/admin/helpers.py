"""Shared helpers for the admin subpackage."""


def _escape_ilike(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _best_effort_delete_media(file_keys: list[str]) -> None:
    """Best-effort MinIO cleanup on admin takedowns (AUT-832 F4). Object removal
    must never fail a moderation delete, so any storage error is swallowed."""
    if not file_keys:
        return
    try:
        from app.core.storage import delete_object

        for key in file_keys:
            await delete_object(key)
    except Exception:
        return