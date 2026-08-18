"""Self-hosted market-data API: live CarsGuide/CarSales listings for the
AutoBrain valuation pipeline (AUT-290).

Same pattern as rego-lookup-api: small FastAPI service, X-API-Key auth,
POST /search. The backend (backend/app/services/market_data.py) calls
{MARKET_DATA_URL}/search and aggregates median/low/high/sample_size itself.

Primary scrape source is CarsGuide's SSR search page (the site is a Nuxt
SSR app whose __NUXT_DATA__ payload embeds the listing set as JSON), which
works over plain HTTP without a browser. CarSales.com.au sits behind Akamai
and its own mace-windu channel; reaching it is tracked as a follow-up.
"""

import hmac
import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from bikesguide import search_bikesguide
from carsguide import search_carsguide

app = FastAPI(title="Market Data API", version="1.2.0")

APP_VERSION = "1.2.0"
API_KEY = os.getenv("API_KEY", "")

# Per-IP and per-API-key limits on /search (each search scrapes listing sites).
# In-memory buckets are fine: each deployment runs a single uvicorn worker.
# Tune with RATE_LIMIT_IP / RATE_LIMIT_KEY env vars.
RATE_LIMIT_IP = os.getenv("RATE_LIMIT_IP", "30/minute")
RATE_LIMIT_KEY = os.getenv("RATE_LIMIT_KEY", "120/minute")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


def _api_key(request: Request) -> str:
    return request.headers.get("x-api-key") or "anon"


limiter = Limiter(key_func=_api_key, headers_enabled=True)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class SearchRequest(BaseModel):
    query: str = ""
    make: str = ""
    model: str = ""
    year: int | None = None
    vehicle_type: str = "car"


class SearchResponse(BaseModel):
    source: str
    listings: list[dict]
    note: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.post("/search", response_model=SearchResponse)
@limiter.limit(RATE_LIMIT_IP, key_func=_client_ip)
@limiter.limit(RATE_LIMIT_KEY, key_func=_api_key)
async def search(request: Request, response: Response, req: SearchRequest, x_api_key: str | None = Header(None)):
    if not API_KEY or not hmac.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="invalid API key")
    query = (req.query or " ".join(x for x in (req.make, req.model) if x)).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query or make/model required")
    vehicle_type = (req.vehicle_type or "car").lower()
    try:
        if vehicle_type in ("motorcycle", "bike", "motorbike"):
            return await search_bikesguide(query, req.year)
        return await search_carsguide(query, req.year)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}")
