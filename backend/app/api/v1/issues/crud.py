from fastapi import APIRouter, HTTPException, Path
from typing import List

router = APIRouter(tags=["issues-crud"])

_ISSUES: List[dict] = []


@router.get("/issues", summary="List issues")
async def list_issues() -> List[dict]:
    return _ISSUES


@router.get("/issues/{issue_id}", summary="Get issue")
async def get_issue(issue_id: str = Path(...)) -> dict:
    for item in _ISSUES:
        if item.get("id") == issue_id:
            return item
    raise HTTPException(status_code=404, detail="Issue not found")


@router.post("/issues", summary="Create issue")
async def create_issue(payload: dict) -> dict:
    item = {"id": str(len(_ISSUES) + 1), **payload}
    _ISSUES.append(item)
    return item


@router.put("/issues/{issue_id}", summary="Update issue")
async def update_issue(issue_id: str, payload: dict) -> dict:
    for item in _ISSUES:
        if item.get("id") == issue_id:
            item.update(payload)
            return item
    raise HTTPException(status_code=404, detail="Issue not found")


@router.delete("/issues/{issue_id}", summary="Delete issue")
async def delete_issue(issue_id: str) -> dict:
    for i, item in enumerate(_ISSUES):
        if item.get("id") == issue_id:
            del _ISSUES[i]
            return {"deleted": issue_id}
    raise HTTPException(status_code=404, detail="Issue not found")
