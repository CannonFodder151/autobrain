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

import os

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from carsguide import search_carsguide

app = FastAPI(title="Market Data API", version="1.0.0")

APP_VERSION = "1.0.0"
API_KEY = os.getenv("API_KEY", "")


class SearchRequest(BaseModel):
    query: str = ""
    make: str = ""
    model: str = ""
    year: int | None = None


class SearchResponse(BaseModel):
    source: str
    listings: list[dict]


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, x_api_key: str | None = Header(None)):
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")
    query = (req.query or " ".join(x for x in (req.make, req.model) if x)).strip()
    if not query:
        raise HTTPException(status_code=400, detail="query or make/model required")
    try:
        return await search_carsguide(query, req.year)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}")
