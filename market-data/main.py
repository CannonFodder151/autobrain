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
import ipaddress
import os

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from bikesguide import search_bikesguide
from carsguide import search_carsguide
from sca import search_sca

APP_VERSION = "1.2.0"
API_KEY = os.getenv("API_KEY", "")

# AUT-1745: disable OpenAPI docs in production (CWE-200 information disclosure).
# Mirrors the backend + rego-lookup-api pattern. Default to production so
# unset ENVIRONMENT does not accidentally expose /docs in prod.
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
docs_url_open = "/docs" if ENVIRONMENT != "production" else None
redoc_url_open = None if ENVIRONMENT != "production" else None
openapi_url_open = None if ENVIRONMENT == "production" else "/openapi.json"

app = FastAPI(
    title="Market Data API",
    version=APP_VERSION,
    docs_url=docs_url_open,
    redoc_url=redoc_url_open,
    openapi_url=openapi_url_open,
)

# Per-IP and per-API-key limits on /search (each search scrapes listing sites).
# In-memory buckets are fine: each deployment runs a single uvicorn worker.
# Tune with RATE_LIMIT_IP / RATE_LIMIT_KEY env vars.
RATE_LIMIT_IP = os.getenv("RATE_LIMIT_IP", "30/minute")
RATE_LIMIT_KEY = os.getenv("RATE_LIMIT_KEY", "120/minute")


# X-Forwarded-For is trusted only when the direct socket peer is in this
# allowlist (comma-separated IPs/CIDRs, e.g. the reverse-proxy docker subnet).
# Unset/empty (the default): the socket address is always used and client XFF
# headers are ignored, so the per-IP limit cannot be evaded by spoofing.
# Mirrors the rego-lookup-api pattern (AUT-1741).
TRUSTED_NETWORKS = [
    ipaddress.ip_network(p.strip(), strict=False)
    for p in os.getenv("TRUSTED_PROXIES", "").split(",")
    if p.strip()
]


def _client_ip(request: Request) -> str:
    peer = get_remote_address(request)
    fwd = request.headers.get("x-forwarded-for")
    if TRUSTED_NETWORKS and fwd:
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return peer
        if any(peer_ip in net for net in TRUSTED_NETWORKS):
            # Rightmost non-trusted hop is the real client; proxies overwrite
            # rather than strip, so walk the chain backwards.
            for hop in reversed([h.strip() for h in fwd.split(",")]):
                try:
                    hop_ip = ipaddress.ip_address(hop)
                except ValueError:
                    return hop
                if not any(hop_ip in net for net in TRUSTED_NETWORKS):
                    return hop
    return peer


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


class SCALookupRequest(BaseModel):
    rego: str = ""
    state: str = ""
    make: str = ""
    model: str = ""
    year: int | None = None


class SCALookupResponse(BaseModel):
    source: str
    vehicle: dict | None = None
    parts: list[dict] = []
    categories: list[dict] = []
    note: str | None = None


@app.post("/sca-parts", response_model=SCALookupResponse)
@limiter.limit(RATE_LIMIT_IP, key_func=_client_ip)
@limiter.limit(RATE_LIMIT_KEY, key_func=_api_key)
async def sca_parts(request: Request, response: Response,
                    req: SCALookupRequest, x_api_key: str | None = Header(None)):
    if not API_KEY or not hmac.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="invalid API key")
    rego = (req.rego or "").strip()
    state = (req.state or "").upper()
    make = (req.make or "").strip()
    model = (req.model or "").strip()
    year = req.year

    try:
        result = await search_sca(rego=rego if rego else None, state=state if state else None,
                                  make=make, model=model, year=year)
        return result
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}")
