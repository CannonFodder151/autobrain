from fastapi import APIRouter, HTTPException, Request

from app.schemas.demo_request import DemoRequest, DemoResponse
from app.services.demo_request import check_rate_limit, is_spam, deliver_credentials

router = APIRouter()


@router.post("/demo/request", response_model=DemoResponse, summary="Request demo access")
async def request_demo(payload: DemoRequest, request: Request) -> DemoResponse:
    if is_spam(payload.model_dump()):
        raise HTTPException(status_code=400, detail="Invalid request")
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(ip, payload.email):
        raise HTTPException(status_code=429, detail="Too many requests")
    result = deliver_credentials(payload.email)
    return DemoResponse(
        status=result["status"],
        message=result["message"],
        login_url=result["login_url"],
    )
