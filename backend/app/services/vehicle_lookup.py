"""Vehicle make/model/year lookup — deterministic data, no AI.

Provides a static dataset of common Australian-market vehicles for
compliance checks. The dataset is intentionally compact; extend as
new models are imported or manufactured for the AU market.
"""
from __future__ import annotations


_VEHICLE_DB: list[dict] = [
    # ── Japanese ──
    {"make": "Toyota", "model": "Supra", "year_from": 1979, "year_to": 2002, "category": "sports", "rhd": True},
    {"make": "Toyota", "model": "Supra", "year_from": 2019, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Toyota", "model": "GT86", "year_from": 2012, "year_to": 2020, "category": "sports", "rhd": True},
    {"make": "Toyota", "model": "GR86", "year_from": 2021, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Toyota", "model": "Corolla", "year_from": 1987, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Toyota", "model": "Camry", "year_from": 1983, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Toyota", "model": "Hilux", "year_from": 1968, "year_to": 2025, "category": "light_truck", "rhd": True},
    {"make": "Toyota", "model": "Land Cruiser", "year_from": 1951, "year_to": 2025, "category": "light_truck", "rhd": True},
    {"make": "Toyota", "model": "Rav4", "year_from": 1994, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Toyota", "model": "MR2", "year_from": 1984, "year_to": 1999, "category": "sports", "rhd": True},
    {"make": "Toyota", "model": "Cressida", "year_from": 1976, "year_to": 1992, "category": "passenger", "rhd": True},
    {"make": "Toyota", "model": "Soarer", "year_from": 1981, "year_to": 2001, "category": "passenger", "rhd": True},
    {"make": "Toyota", "model": "Chaser", "year_from": 1977, "year_to": 2001, "category": "passenger", "rhd": True},
    {"make": "Toyota", "model": "Mark II", "year_from": 1968, "year_to": 2004, "category": "passenger", "rhd": True},
    {"make": "Nissan", "model": "Skyline GT-R", "year_from": 1969, "year_to": 2002, "category": "sports", "rhd": True},
    {"make": "Nissan", "model": "Silvia", "year_from": 1965, "year_to": 2002, "category": "sports", "rhd": True},
    {"make": "Nissan", "model": "180SX", "year_from": 1988, "year_to": 1998, "category": "sports", "rhd": True},
    {"make": "Nissan", "model": "240SX", "year_from": 1989, "year_to": 1998, "category": "sports", "rhd": False},
    {"make": "Nissan", "model": "350Z", "year_from": 2002, "year_to": 2009, "category": "sports", "rhd": True},
    {"make": "Nissan", "model": "370Z", "year_from": 2009, "year_to": 2020, "category": "sports", "rhd": True},
    {"make": "Nissan", "model": "R35 GT-R", "year_from": 2008, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Nissan", "model": "Navara", "year_from": 1986, "year_to": 2025, "category": "light_truck", "rhd": True},
    {"make": "Nissan", "model": "Patrol", "year_from": 1951, "year_to": 2025, "category": "light_truck", "rhd": True},
    {"make": "Mitsubishi", "model": "Lancer Evolution", "year_from": 1992, "year_to": 2015, "category": "sports", "rhd": True},
    {"make": "Mitsubishi", "model": "Eclipse", "year_from": 1989, "year_to": 1999, "category": "sports", "rhd": False},
    {"make": "Mitsubishi", "model": "Pajero", "year_from": 1982, "year_to": 2021, "category": "light_truck", "rhd": True},
    {"make": "Mitsubishi", "model": "Triton", "year_from": 1978, "year_to": 2025, "category": "light_truck", "rhd": True},
    {"make": "Mazda", "model": "RX-7", "year_from": 1978, "year_to": 2002, "category": "sports", "rhd": True},
    {"make": "Mazda", "model": "RX-8", "year_from": 2003, "year_to": 2012, "category": "sports", "rhd": True},
    {"make": "Mazda", "model": "MX-5", "year_from": 1989, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Mazda", "model": "3", "year_from": 2003, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Mazda", "model": "6", "year_from": 2002, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Subaru", "model": "Impreza WRX STI", "year_from": 1994, "year_to": 2017, "category": "sports", "rhd": True},
    {"make": "Subaru", "model": "BRZ", "year_from": 2012, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Subaru", "model": "Forester", "year_from": 1997, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Honda", "model": "NSX", "year_from": 1990, "year_to": 2005, "category": "sports", "rhd": True},
    {"make": "Honda", "model": "S2000", "year_from": 1999, "year_to": 2009, "category": "sports", "rhd": True},
    {"make": "Honda", "model": "Civic Type R", "year_from": 1997, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Honda", "model": "Civic", "year_from": 1973, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Honda", "model": "Accord", "year_from": 1976, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Honda", "model": "CR-V", "year_from": 1995, "year_to": 2025, "category": "passenger", "rhd": True},
    # ── European ──
    {"make": "BMW", "model": "M3 (E30)", "year_from": 1986, "year_to": 1991, "category": "sports", "rhd": True},
    {"make": "BMW", "model": "M3 (E36)", "year_from": 1992, "year_to": 1999, "category": "sports", "rhd": True},
    {"make": "BMW", "model": "M3 (E46)", "year_from": 2000, "year_to": 2006, "category": "sports", "rhd": True},
    {"make": "BMW", "model": "M3 (E90)", "year_from": 2007, "year_to": 2013, "category": "sports", "rhd": True},
    {"make": "BMW", "model": "M3 (G80)", "year_from": 2021, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "BMW", "model": "1 Series", "year_from": 2004, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "BMW", "model": "3 Series", "year_from": 1975, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Porsche", "model": "911 (993)", "year_from": 1994, "year_to": 1998, "category": "sports", "rhd": True},
    {"make": "Porsche", "model": "911 (996)", "year_from": 1997, "year_to": 2004, "category": "sports", "rhd": True},
    {"make": "Porsche", "model": "911 (997)", "year_from": 2004, "year_to": 2012, "category": "sports", "rhd": True},
    {"make": "Porsche", "model": "911 (991)", "year_from": 2012, "year_to": 2019, "category": "sports", "rhd": True},
    {"make": "Porsche", "model": "911 (992)", "year_from": 2019, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Porsche", "model": "Cayman", "year_from": 2005, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Volkswagen", "model": "Golf GTI", "year_from": 1976, "year_to": 2025, "category": "passenger", "rhd": True},
    {"make": "Mercedes-Benz", "model": "AMG GT", "year_from": 2014, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Audi", "model": "RS3", "year_from": 2011, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Audi", "model": "TT RS", "year_from": 2009, "year_to": 2025, "category": "sports", "rhd": True},
    {"make": "Jaguar", "model": "F-Type", "year_from": 2013, "year_to": 2024, "category": "sports", "rhd": True},
    {"make": "Lotus", "model": "Elise", "year_from": 1996, "year_to": 2021, "category": "sports", "rhd": True},
    {"make": "Lotus", "model": "Exige", "year_from": 2000, "year_to": 2025, "category": "sports", "rhd": True},
    # ── American ──
    {"make": "Ford", "model": "Mustang", "year_from": 1964, "year_to": 2025, "category": "sports", "rhd": False},
    {"make": "Ford", "model": "Focus ST", "year_from": 2005, "year_to": 2018, "category": "passenger", "rhd": True},
    {"make": "Chevrolet", "model": "Corvette", "year_from": 1953, "year_to": 2025, "category": "sports", "rhd": False},
    {"make": "Chevrolet", "model": "Camaro", "year_from": 1966, "year_to": 2025, "category": "sports", "rhd": False},
    {"make": "Dodge", "model": "Challenger", "year_from": 1970, "year_to": 2023, "category": "sports", "rhd": False},
    {"make": "Dodge", "model": "Charger", "year_from": 1966, "year_to": 2023, "category": "passenger", "rhd": False},
    {"make": "Jeep", "model": "Wrangler", "year_from": 1986, "year_to": 2025, "category": "light_truck", "rhd": False},
    {"make": "Tesla", "model": "Model 3", "year_from": 2017, "year_to": 2025, "category": "passenger", "rhd": False},
    {"make": "Tesla", "model": "Model Y", "year_from": 2020, "year_to": 2025, "category": "passenger", "rhd": False},
    # ── Australian ──
    {"make": "Holden", "model": "Commodore", "year_from": 1978, "year_to": 2020, "category": "passenger", "rhd": True},
    {"make": "Holden", "model": "Monaro", "year_from": 1968, "year_to": 2006, "category": "sports", "rhd": True},
    {"make": "Holden", "model": "Colorado", "year_from": 2008, "year_to": 2020, "category": "light_truck", "rhd": True},
    {"make": "Ford", "model": "Falcon", "year_from": 1960, "year_to": 2016, "category": "passenger", "rhd": True},
    {"make": "Ford", "model": "Ranger", "year_from": 2011, "year_to": 2025, "category": "light_truck", "rhd": True},
    {"make": "Ford", "model": "Raptor", "year_from": 2018, "year_to": 2025, "category": "light_truck", "rhd": True},
]


def lookup_vehicle(make: str, model: str | None = None, year: int | None = None) -> list[dict]:
    """Find matching vehicles from the built-in AU database.

    Returns up to 20 matches. At least `make` is required.
    """
    make_lower = make.lower()
    results = [v for v in _VEHICLE_DB if v["make"].lower() == make_lower]

    if model:
        model_lower = model.lower()
        results = [v for v in results if model_lower in v["model"].lower()]

    if year is not None:
        results = [v for v in results if v["year_from"] <= year <= v["year_to"]]

    return results[:20]


def get_available_makes() -> list[str]:
    """Return a sorted list of unique makes in the database."""
    return sorted({v["make"] for v in _VEHICLE_DB})


def get_models_for_make(make: str) -> list[str]:
    """Return models available for a given make."""
    return sorted({v["model"] for v in _VEHICLE_DB if v["make"].lower() == make.lower()})


def get_year_range(make: str, model: str) -> dict:
    """Return the year range for a specific make/model."""
    matches = [
        v for v in _VEHICLE_DB
        if v["make"].lower() == make.lower() and v["model"].lower() == model.lower()
    ]
    if not matches:
        return {"make": make, "model": model, "year_from": None, "year_to": None, "found": False}
    return {
        "make": make,
        "model": model,
        "year_from": min(v["year_from"] for v in matches),
        "year_to": max(v["year_to"] for v in matches),
        "found": True,
    }
