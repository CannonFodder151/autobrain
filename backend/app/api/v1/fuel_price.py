from fastapi import APIRouter, Path

from app.schemas.fuel_price import FeedHealthResponse, FuelPriceResponse
from app.services.fuel_price import fetch_state, all_feed_health

router = APIRouter()


@router.get(
    "/fuel-price/{state}",
    response_model=FuelPriceResponse,
    summary="Get fuel prices for a state",
    description="Returns live fuel prices for the requested state. WA (official feed) and QLD (partner feed) are live. NSW/ACT/VIC are pending partner-feed keys.",
)
async def get_fuel_price(
    state: str = Path(..., description="Australian state code (WA, QLD, NSW, ACT, VIC)", min_length=2, max_length=3),
) -> FuelPriceResponse:
    state = state.upper()
    result = fetch_state(state)
    return FuelPriceResponse(**result)


@router.get(
    "/fuel-price",
    response_model=FuelPriceResponse,
    summary="Get fuel prices for default state (WA)",
    description="Returns live fuel prices for WA as the default state.",
)
async def get_fuel_price_default() -> FuelPriceResponse:
    result = fetch_state("WA")
    return FuelPriceResponse(**result)


@router.get(
    "/fuel-price/feeds/health",
    response_model=FeedHealthResponse,
    summary="Get feed health for all states",
    description="Returns the health/status of each state's fuel price feed.",
)
async def get_feed_health() -> FeedHealthResponse:
    feeds = all_feed_health()
    return FeedHealthResponse(feeds=feeds)