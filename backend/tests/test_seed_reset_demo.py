"""reset_demo must clear vehicle_shares before deleting the demo account (AUT-521).

A demo reset deletes the demo user + all demo vehicles. If a share references
a demo vehicle or the demo user, the FK (NO ACTION) blocks the deletes on
Postgres and the reset crashes at boot; on FK-less backends it leaves orphaned
shares. Regression: reset_demo removes those shares first. Foreign keys are
enforced (PRAGMA) so the ordering is tested like it would be on Postgres.

Run (sqlite, no Postgres/MinIO needed):
    cd backend && python3 -m pytest tests/test_seed_reset_demo.py -q
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/autobrain-seed-reset-test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DEMO_MODE"] = "true"
os.environ["DEMO_EMAIL"] = "demo@test.local"
os.environ["DEMO_PASSWORD"] = "demo"
os.environ["DEMO_DISPLAY_NAME"] = "Demo Garage"
os.environ["POSTGRES_USER"] = "autobrain"
os.environ["POSTGRES_PASSWORD"] = "autobrain"
os.environ["POSTGRES_DB"] = "autobrain"
os.environ["MINIO_ACCESS_KEY"] = "autobrain"
os.environ["MINIO_SECRET_KEY"] = "autobrain"
os.environ["MINIO_BUCKET"] = "autobrain-assets"
os.environ["MINIO_ENDPOINT"] = "minio:9000"
os.environ["AI_GATEWAY_API_KEY"] = "test-ai-key"
os.environ["ADMIN_API_KEY"] = "test-admin-key-0123456789-0123456789"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""

import pytest  # noqa: E402
from sqlalchemy import event, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.seed import reset_demo, seed_demo  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.share import VehicleShare  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.social.models import SocialIssueComment, SocialIssuePost  # noqa: E402

# Settings is a process-wide singleton cached on first app import; another test
# module may have imported it before our env vars above ran, so pin the demo
# config directly on the cached instance instead of relying on os.environ.
settings.DEMO_MODE = True
settings.DEMO_EMAIL = "demo@test.local"
settings.DEMO_PASSWORD = "demo"
settings.DEMO_DISPLAY_NAME = "Demo Garage"

# Self-contained sqlite engine: seed.py resolves SessionLocal from
# app.db.session at call time, so patch it to our test sessionmaker. Using the
# shared app engine here would break if an earlier test module imported it with
# a Postgres DATABASE_URL.
engine = create_async_engine("sqlite+aiosqlite:////tmp/autobrain-seed-reset-test.db")
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "connect")
def _enforce_fks(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


import app.db.seed as seed_module  # noqa: E402

seed_module.SessionLocal = SessionLocal


async def _reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_reset_demo_clears_shares(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.db.seed._upload_demo_image",
        lambda *a, **k: "https://minio.local/x.png",
    )
    await _reset_schema()
    await seed_demo()

    async with SessionLocal() as db:
        demo = await db.scalar(select(User).where(User.email == "demo@test.local"))
        demo_vehicle = await db.scalar(
            select(Vehicle).where(Vehicle.user_id == demo.id)
        )
        staff = User(
            email="staff@test.local",
            display_name="Staff",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
        )
        db.add(staff)
        await db.flush()
        staff_vehicle = Vehicle(user_id=staff.id, nickname="Staff car")
        db.add(staff_vehicle)
        await db.flush()
        db.add_all(
            [
                VehicleShare(vehicle_id=demo_vehicle.id, invitee_user_id=staff.id),
                VehicleShare(vehicle_id=staff_vehicle.id, invitee_user_id=demo.id),
            ]
        )
        await db.commit()

    await reset_demo()

    async with SessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(VehicleShare))
        assert count == 0, "reset_demo left vehicle_shares behind"
        demo_after = await db.scalar(
            select(User).where(User.email == "demo@test.local")
        )
        assert demo_after is not None, "reset_demo failed to re-seed the demo user"


@pytest.mark.asyncio
async def test_demo_seeds_issues_blog_and_reset_cleans_it(monkeypatch) -> None:
    """Demo seed ships >=15 issue-blog posts with replies (AUT-712).

    Answered/resolved posts must pin an answer comment. reset_demo must clear
    the demo user's posts (and their replies/flags) before deleting the user —
    enforced FKs would otherwise crash the reset on Postgres.
    """
    monkeypatch.setattr(
        "app.db.seed._upload_demo_image",
        lambda *a, **k: "https://minio.local/x.png",
    )
    await _reset_schema()
    await seed_demo()

    async with SessionLocal() as db:
        demo = await db.scalar(select(User).where(User.email == "demo@test.local"))
        posts = list((await db.scalars(
            select(SocialIssuePost).where(SocialIssuePost.author_user_id == demo.id)
        )).all())
        assert len(posts) >= 15, f"expected >=15 demo posts, got {len(posts)}"
        for post in posts:
            assert post.tags, "demo post should carry deterministic tags"
            comments = list((await db.scalars(
                select(SocialIssueComment).where(SocialIssueComment.post_id == post.id)
            )).all())
            assert comments, f"post has no replies: {post.title}"
            if post.status in ("answered", "resolved"):
                assert post.resolved_comment_id, f"{post.status} post lacks pinned answer"

    await reset_demo()

    async with SessionLocal() as db:
        # reset_demo wipes then re-seeds: the demo user + issue blog must exist
        # again (reset completes without an FK crash on the issue-blog rows).
        demo_after = await db.scalar(select(User).where(User.email == "demo@test.local"))
        assert demo_after is not None, "reset_demo failed to re-seed the demo user"
        reposted = list((await db.scalars(
            select(SocialIssuePost).where(SocialIssuePost.author_user_id == demo_after.id)
        )).all())
        assert len(reposted) >= 15, "reset_demo failed to re-seed the issue blog"
