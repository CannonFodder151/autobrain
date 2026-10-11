"""Fuel Feeds — deterministic ingest for WA/NSW/VIC/QLD price feeds.

All public names are re-exported so existing imports continue to work.
"""

from app.services.fuel_feeds.common import (
    _FUEL_TYPE_MAP,
    _now,
    _to_float,
    _to_dt,
    _first,
    _normalise_fuel_type,
    haversine_km,
    DEFAULT_FUEL_TYPES,
    BRAND_LOGOS,
    PRICE_HISTORY_DAYS,
    _day_bucket,
)  # noqa: F401

from app.services.fuel_feeds.wa import (
    _parse_wa_sites,
    _parse_wa_prices,
    ingest_wa_fuelwatch,
)  # noqa: F401

from app.services.fuel_feeds.nsw import (
    _parse_nsw,
    ingest_nsw_fuelcheck,
)  # noqa: F401

from app.services.fuel_feeds.vic import (
    _parse_vic,
    ingest_vic_fuel_saver,
)  # noqa: F401

from app.services.fuel_feeds.qld import (
    _parse_qld_direct_sites,
    _parse_qld_direct_prices,
    _parse_qld_brands,
    _parse_qld_fuel_types,
    _parse_qld_geo_regions,
    _parse_qld,
    _fetch_qld_direct,
    ingest_qld_fuel_prices,
)  # noqa: F401

from app.services.fuel_feeds.persistence import (
    _upsert_station,
    _replace_station_prices,
    _ingest,
    FuelPriceArbitration,
    RawSourceObservation,
    arbitrate_station_day,
    arbitrate_all_recent,
    source_authority,
    arbitrate,
)  # noqa: F401

from app.services.fuel_feeds.network import (
    _fetch_json,
)  # noqa: F401

from app.services.fuel_feeds.orchestrator import (
    ingest_all_fuel,
)  # noqa: F401

__all__ = [
    # Common
    "_FUEL_TYPE_MAP",
    "_now",
    "_to_float",
    "_to_dt",
    "_first",
    "_normalise_fuel_type",
    "haversine_km",
    "DEFAULT_FUEL_TYPES",
    "BRAND_LOGOS",
    "PRICE_HISTORY_DAYS",
    "_day_bucket",
    # WA
    "_parse_wa_sites",
    "_parse_wa_prices",
    "ingest_wa_fuelwatch",
    # NSW
    "_parse_nsw",
    "ingest_nsw_fuelcheck",
    # VIC
    "_parse_vic",
    "ingest_vic_fuel_saver",
    # QLD
    "_parse_qld_direct_sites",
    "_parse_qld_direct_prices",
    "_parse_qld_brands",
    "_parse_qld_fuel_types",
    "_parse_qld_geo_regions",
    "_parse_qld",
    "_fetch_qld_direct",
    "ingest_qld_fuel_prices",
    # Persistence
    "_upsert_station",
    "_replace_station_prices",
    "_ingest",
    "FuelPriceArbitration",
    "RawSourceObservation",
    "arbitrate_station_day",
    "arbitrate_all_recent",
    "source_authority",
    "arbitrate",
    # Network
    "_fetch_json",
    # Orchestrator
    "ingest_all_fuel",
]