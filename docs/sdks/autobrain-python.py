#!/usr/bin/env python3
"""
AutoBrain Python SDK v1
Usage: pip install httpx
"""

import httpx
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class Vehicle:
    id: str
    nickname: str
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    odometer_km: Optional[int] = None
    rego: Optional[str] = None


@dataclass
class ServiceRecord:
    id: str
    vehicle_id: str
    service_date: str
    odometer_km: int
    service_type: str
    description: str
    cost: float
    status: str


@dataclass
class FuelLog:
    id: str
    vehicle_id: str
    fill_date: str
    litres: float
    price_per_litre: float
    odometer_km: int
    total_cost: float


class AutoBrainError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"{status}: {message}")


class AutoBrainClient:
    """Async client for AutoBrain Public API v1."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.autobrain.app/api/v1",
        timeout: float = 30.0
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise AutoBrainError(resp.status_code, resp.text)
        if resp.status_code == 204:
            return None
        return resp.json()

    # --- Vehicles ---
    async def list_vehicles(self) -> List[Vehicle]:
        data = await self._request("GET", "/vehicles")
        return [Vehicle(**v) for v in data]

    async def get_vehicle(self, vehicle_id: str) -> Vehicle:
        data = await self._request("GET", f"/vehicles/{vehicle_id}")
        return Vehicle(**data)

    async def create_vehicle(self, **kwargs) -> Vehicle:
        data = await self._request("POST", "/vehicles", json=kwargs)
        return Vehicle(**data)

    async def update_vehicle(self, vehicle_id: str, **kwargs) -> Vehicle:
        data = await self._request("PATCH", f"/vehicles/{vehicle_id}", json=kwargs)
        return Vehicle(**data)

    async def delete_vehicle(self, vehicle_id: str) -> None:
        await self._request("DELETE", f"/vehicles/{vehicle_id}")

    async def get_timeline(self, vehicle_id: str) -> List[Dict]:
        return await self._request("GET", f"/vehicles/{vehicle_id}/timeline")

    # --- Services ---
    async def list_services(self, vehicle_id: str) -> List[ServiceRecord]:
        data = await self._request("GET", f"/vehicles/{vehicle_id}/services")
        return [ServiceRecord(**s) for s in data]

    async def get_service(self, vehicle_id: str, service_id: str) -> ServiceRecord:
        data = await self._request("GET", f"/vehicles/{vehicle_id}/services/{service_id}")
        return ServiceRecord(**data)

    async def create_service(self, vehicle_id: str, **kwargs) -> ServiceRecord:
        data = await self._request("POST", f"/vehicles/{vehicle_id}/services", json=kwargs)
        return ServiceRecord(**data)

    async def update_service(self, vehicle_id: str, service_id: str, **kwargs) -> ServiceRecord:
        data = await self._request("PATCH", f"/vehicles/{vehicle_id}/services/{service_id}", json=kwargs)
        return ServiceRecord(**data)

    async def delete_service(self, vehicle_id: str, service_id: str) -> None:
        await self._request("DELETE", f"/vehicles/{vehicle_id}/services/{service_id}")

    # --- Fuel ---
    async def list_fuel(self, vehicle_id: str, fy: Optional[int] = None) -> List[FuelLog]:
        params = {"fy": fy} if fy else None
        data = await self._request("GET", f"/vehicles/{vehicle_id}/fuel", params=params)
        return [FuelLog(**f) for f in data]

    async def add_fuel(
        self,
        vehicle_id: str,
        litres: float,
        price_per_litre: float,
        odometer_km: int,
        fill_date: Optional[str] = None,
        **kwargs
    ) -> FuelLog:
        payload = {"litres": litres, "price_per_litre": price_per_litre, "odometer_km": odometer_km}
        if fill_date:
            payload["fill_date"] = fill_date
        payload.update(kwargs)
        data = await self._request("POST", f"/vehicles/{vehicle_id}/fuel", json=payload)
        return FuelLog(**data)

    async def get_fuel_stats(self, vehicle_id: str) -> Dict:
        return await self._request("GET", f"/vehicles/{vehicle_id}/fuel/stats")

    # --- Diagnostics ---
    async def run_diagnostics(
        self,
        vehicle_id: str,
        symptoms: str,
        obd_codes: Optional[List[str]] = None,
        vehicle_context: Optional[Dict] = None
    ) -> Dict:
        payload = {"symptoms": symptoms}
        if obd_codes:
            payload["obd_codes"] = obd_codes
        if vehicle_context:
            payload["vehicle_context"] = vehicle_context
        return await self._request("POST", f"/vehicles/{vehicle_id}/diagnostics", json=payload)

    async def list_diagnostics(self, vehicle_id: str) -> List[Dict]:
        return await self._request("GET", f"/vehicles/{vehicle_id}/diagnostics")

    # --- Logbook ---
    async def list_logbook(self, vehicle_id: str, fy: Optional[int] = None) -> List[Dict]:
        params = {"fy": fy} if fy else None
        return await self._request("GET", f"/vehicles/{vehicle_id}/logbook", params=params)

    async def start_trip(self, vehicle_id: str, started_at: str, start_odometer_km: int, **kwargs) -> Dict:
        payload = {"started_at": started_at, "start_odometer_km": start_odometer_km}
        payload.update(kwargs)
        return await self._request("POST", f"/vehicles/{vehicle_id}/logbook", json=payload)

    async def end_trip(self, vehicle_id: str, entry_id: str, ended_at: str, end_odometer_km: int, **kwargs) -> Dict:
        payload = {"ended_at": ended_at, "end_odometer_km": end_odometer_km, "status": "completed"}
        payload.update(kwargs)
        return await self._request("PATCH", f"/vehicles/{vehicle_id}/logbook/{entry_id}", json=payload)

    # --- Webhooks ---
    async def list_webhooks(self) -> List[Dict]:
        return await self._request("GET", "/developer/webhooks")

    async def create_webhook(
        self,
        label: str,
        url: str,
        events: List[str],
        max_retries: int = 5
    ) -> Dict:
        payload = {"label": label, "url": url, "events": events, "max_retries": max_retries}
        return await self._request("POST", "/developer/webhooks", json=payload)

    async def delete_webhook(self, webhook_id: str) -> None:
        await self._request("DELETE", f"/developer/webhooks/{webhook_id}")


# --- Example Usage ---
async def main():
    import os
    api_key = os.environ.get("AUTOBRAIN_API_KEY")
    if not api_key:
        print("Set AUTOBRAIN_API_KEY environment variable")
        return

    async with AutoBrainClient(api_key) as client:
        # List vehicles
        vehicles = await client.list_vehicles()
        print(f"Found {len(vehicles)} vehicles:")
        for v in vehicles:
            print(f"  - {v.nickname} ({v.make} {v.model} {v.year}) - {v.odometer_km}km")

        # Add a fuel entry for the first vehicle
        if vehicles:
            v = vehicles[0]
            fuel = await client.add_fuel(
                vehicle_id=v.id,
                litres=45.5,
                price_per_litre=1.89,
                odometer_km=v.odometer_km or 0
            )
            print(f"\nAdded fuel: {fuel.litres}L @ ${fuel.price_per_litre}/L = ${fuel.total_cost}")

        # List recent services
        for v in vehicles[:1]:
            services = await client.list_services(v.id)
            print(f"\nServices for {v.nickname}:")
            for s in services[:3]:
                print(f"  - {s.service_date}: {s.service_type} (${s.cost})")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())