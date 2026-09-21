"""Engineer marketplace search service (AUT-3661).

Implements geospatial search, specialty filtering, rating, price, and
availability filters with pagination and sorting.
"""

import math
from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.models.engineer import Engineer, EngineerReview
from app.schemas.engineer import EngineerSearchFilters, EngineerSearchResult

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger(__name__)

# Australian postcodes to (lat, lon) approximations for radius search.
# In production this would be a proper postcode lookup table.
POSTCODE_CENTROIDS = {
    "2000": (-33.8688, 151.2093),  # Sydney
    "2001": (-33.8688, 151.2093),
    "3000": (-37.8136, 144.9631),  # Melbourne
    "3001": (-37.8136, 144.9631),
    "4000": (-27.4698, 153.0251),  # Brisbane
    "4001": (-27.4698, 153.0251),
    "5000": (-34.9285, 138.6007),  # Adelaide
    "5001": (-34.9285, 138.6007),
    "6000": (-31.9505, 115.8605),  # Perth
    "6001": (-31.9505, 115.8605),
    "7000": (-42.8821, 147.3272),  # Hobart
    "7001": (-42.8821, 147.3272),
    "2600": (-35.2809, 149.1300),  # Canberra
    "2601": (-35.2809, 149.1300),
    "0800": (-12.4634, 130.8456),  # Darwin
    "0801": (-12.4634, 130.8456),
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres (WGS84)."""
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _resolve_location(
    postcode: str | None,
    lat: float | None,
    lon: float | None,
) -> tuple[float | None, float | None]:
    """Resolve search center from postcode or direct lat/lon."""
    if lat is not None and lon is not None:
        return lat, lon
    if postcode and postcode in POSTCODE_CENTROIDS:
        return POSTCODE_CENTROIDS[postcode]
    return None, None


async def search_engineers(
    db: AsyncSession,
    filters: EngineerSearchFilters,
    page: int = 1,
    limit: int = 20,
    sort: str = "rating",
    order: str = "desc",
) -> tuple[list[EngineerSearchResult], int]:
    """Search engineers with all filters, pagination, and sorting.

    Returns (results, total_count).
    """
    # Resolve geospatial center
    center_lat, center_lon = _resolve_location(filters.postcode, filters.lat, filters.lon)

    # Build base query
    stmt = select(Engineer).where(Engineer.is_active.is_(True))

    # Keyword search across name, specialties, certifications
    if filters.q:
        escaped = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(
            or_(
                Engineer.display_name.ilike(f"%{escaped}%", escape="\\"),
            )
        )

    # Specialty multi-select (AND - must have ALL specified specialties)
    if filters.specialties:
        for spec in filters.specialties:
            stmt = stmt.where(Engineer.specialties.contains([spec]))

    # Minimum rating
    if filters.min_rating is not None:
        stmt = stmt.where(Engineer.rating >= filters.min_rating)

    # Price range (uses price_per_hour as primary price indicator)
    if filters.price_min is not None:
        stmt = stmt.where(
            or_(
                and_(Engineer.price_per_hour.is_not(None), Engineer.price_per_hour >= filters.price_min),
                and_(Engineer.price_per_job_min.is_not(None), Engineer.price_per_job_min >= filters.price_min),
            )
        )
    if filters.price_max is not None:
        stmt = stmt.where(
            or_(
                and_(Engineer.price_per_hour.is_not(None), Engineer.price_per_hour <= filters.price_max),
                and_(Engineer.price_per_job_max.is_not(None), Engineer.price_per_job_max <= filters.price_max),
            )
        )

    # Availability window filter
    if filters.available_day is not None or filters.available_from is not None or filters.available_to is not None:
        avail_filters = []
        if filters.available_day is not None:
            day_idx = filters.available_day - 1
            avail_filters.append(
                text(f"EXISTS (SELECT 1 FROM jsonb_array_elements(availability) AS a WHERE (a->>'day')::int = {day_idx})")
            )
        if filters.available_from is not None:
            time_str = filters.available_from.strftime("%H:%M:%S")
            avail_filters.append(
                text(f"EXISTS (SELECT 1 FROM jsonb_array_elements(availability) AS a WHERE (a->>'start')::time >= '{time_str}')")
            )
        if filters.available_to is not None:
            time_str = filters.available_to.strftime("%H:%M:%S")
            avail_filters.append(
                text(f"EXISTS (SELECT 1 FROM jsonb_array_elements(availability) AS a WHERE (a->>'end')::time <= '{time_str}')")
            )
        if avail_filters:
            stmt = stmt.where(and_(*avail_filters))

    # Count total before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Apply sorting
    if sort == "distance" and center_lat is not None and center_lon is not None:
        distance_expr = text(
            f"6371 * 2 * asin(sqrt("
            f"  pow(sin(radians(lat - {center_lat}) / 2), 2) + "
            f"  cos(radians(lat)) * cos(radians({center_lat})) * "
            f"  pow(sin(radians(lon - {center_lon}) / 2), 2)"
            f"))"
        )
        if order == "asc":
            stmt = stmt.order_by(distance_expr.asc())
        else:
            stmt = stmt.order_by(distance_expr.desc())
    elif sort == "rating":
        if order == "asc":
            stmt = stmt.order_by(Engineer.rating.asc())
        else:
            stmt = stmt.order_by(Engineer.rating.desc())
    elif sort == "price":
        if order == "asc":
            stmt = stmt.order_by(Engineer.price_per_hour.asc().nullslast())
        else:
            stmt = stmt.order_by(Engineer.price_per_hour.desc().nullslast())
    else:
        stmt = stmt.order_by(Engineer.rating.desc())

    # Pagination
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    # Execute
    rows = (await db.execute(stmt)).scalars().all()

    # Build results with distance
    results: list[EngineerSearchResult] = []
    for eng in rows:
        dist_km = None
        if center_lat is not None and center_lon is not None and eng.lat is not None and eng.lon is not None:
            dist_km = round(_haversine_km(center_lat, center_lon, eng.lat, eng.lon), 1)
        results.append(
            EngineerSearchResult(
                id=eng.id,
                display_name=eng.display_name,
                specialties=eng.specialties or [],
                certifications=eng.certifications or [],
                rating=eng.rating,
                review_count=eng.review_count,
                price_per_hour=eng.price_per_hour,
                price_per_job_min=eng.price_per_job_min,
                price_per_job_max=eng.price_per_job_max,
                years_experience=eng.years_experience,
                is_verified=eng.is_verified,
                is_active=eng.is_active,
                lat=eng.lat,
                lon=eng.lon,
                distance_km=dist_km,
            )
        )

    return results, total


async def get_engineer_by_id(
    db: AsyncSession,
    engineer_id: str,
    load_reviews: bool = True,
) -> Engineer | None:
    """Fetch a single engineer by ID, optionally loading reviews."""
    if load_reviews:
        stmt = (
            select(Engineer)
            .options(selectinload(Engineer.reviews))
            .where(Engineer.id == engineer_id)
        )
    else:
        stmt = select(Engineer).where(Engineer.id == engineer_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_engineer(
    db: AsyncSession,
    data: dict,
) -> Engineer:
    """Create a new engineer profile."""
    eng = Engineer(**data)
    db.add(eng)
    await db.commit()
    await db.refresh(eng)
    return eng


async def add_review(
    db: AsyncSession,
    engineer_id: str,
    user_id: str,
    rating: int,
    title: str | None = None,
    body: str | None = None,
    service_type: str | None = None,
    cost: float | None = None,
    vehicle_id: str | None = None,
) -> EngineerReview:
    """Add a review for an engineer and update their aggregate rating."""
    review = EngineerReview(
        engineer_id=engineer_id,
        user_id=user_id,
        vehicle_id=vehicle_id,
        rating=rating,
        title=title,
        body=body,
        service_type=service_type,
        cost=cost,
    )
    db.add(review)

    # Recalculate engineer rating
    await _recalculate_rating(db, engineer_id)

    await db.commit()
    await db.refresh(review)
    return review


async def _recalculate_rating(db: AsyncSession, engineer_id: str) -> None:
    """Recalculate engineer's average rating from reviews."""
    result = await db.execute(
        select(func.avg(EngineerReview.rating), func.count(EngineerReview.id))
        .where(EngineerReview.engineer_id == engineer_id)
    )
    avg_rating, count = result.one()
    if avg_rating is not None:
        await db.execute(
            text("UPDATE engineers SET rating = :rating, review_count = :count WHERE id = :id"),
            {"rating": round(float(avg_rating), 2), "count": count, "id": engineer_id},
        )
        await db.commit()
