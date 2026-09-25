"""Community Garage (social) module contract.

Actual implementations live in:
- app.social.models (SocialIssuePost, SocialComment, SocialBuild, SocialFlag)
- app.social.federation (cross-server federation)
- app.social.media (image/video uploads)
- app.social.rate_limit (per-user social rate limiting)
- app.social.snapshot (vehicle build snapshots)
- app.social.tags (tag system)
"""

__all__ = [
    "SocialIssuePost",
    "SocialComment",
    "SocialBuild",
    "SocialFlag",
    "register_with_hub",
    "sync_federation",
    "upload_social_media",
    "check_social_rate_limit",
    "create_build_snapshot",
    "get_social_tags",
]


def __getattr__(name: str):
    if name in {
        "SocialIssuePost", "SocialComment", "SocialBuild", "SocialFlag"
    }:
        from app.social.models import SocialIssuePost, SocialComment, SocialBuild, SocialFlag
        globals().update({
            "SocialIssuePost": SocialIssuePost,
            "SocialComment": SocialComment,
            "SocialBuild": SocialBuild,
            "SocialFlag": SocialFlag,
        })
        return globals()[name]
    if name in {
        "register_with_hub", "sync_federation"
    }:
        from app.social.federation import register_with_hub, sync_federation
        globals().update({
            "register_with_hub": register_with_hub,
            "sync_federation": sync_federation,
        })
        return globals()[name]
    if name == "upload_social_media":
        from app.social.media import upload_social_media
        globals()["upload_social_media"] = upload_social_media
        return upload_social_media
    if name == "check_social_rate_limit":
        from app.social.rate_limit import check_social_rate_limit
        globals()["check_social_rate_limit"] = check_social_rate_limit
        return check_social_rate_limit
    if name == "create_build_snapshot":
        from app.social.snapshot import create_build_snapshot
        globals()["create_build_snapshot"] = create_build_snapshot
        return create_build_snapshot
    if name == "get_social_tags":
        from app.social.tags import get_social_tags
        globals()["get_social_tags"] = get_social_tags
        return get_social_tags
    raise AttributeError(f"module 'app.modules.social' has no attribute '{name}'")