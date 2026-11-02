from fastapi import APIRouter, Query

router = APIRouter(tags=["issues-search"])


@router.get("/issues/search", summary="Search issues")
async def search_issues(q: str = Query(..., min_length=1)) -> list:
    # Minimal in-memory search placeholder; real impl queries store.
    return []
