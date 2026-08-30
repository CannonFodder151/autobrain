"""Deterministic fallback for the SCA parts-guide formatter.

Maps raw Supercheap Auto parts-guide categories onto a normalised
Inventory-like part suggestion and classifies each into a service group.
The 9Router layer (see ai router_client "parts-guide" prompt) only *tidies*
descriptions / brands / categories — it never overrides the deterministic
classification or invents parts that aren't in the source taxonomy.
"""

_SCA_FALLBACK_PARTS = {
    "brakes": {"name": "Brake Pads", "category": "brake_pads",
               "description": "Standard replacement brake pads.", "brand": "SCA"},
    "cooling": {"name": "Coolant", "category": "coolant",
                "description": "Long-life coolant flush & replace.", "brand": "SCA"},
    "engine": {"name": "Engine Oil & Filter", "category": "engine_oil",
               "description": "Full synthetic engine oil and filter kit.", "brand": "SCA"},
    "fuel": {"name": "Fuel Filter", "category": "fuel_filter",
             "description": "Replacement fuel filter element.", "brand": "SCA"},
    "transmission": {"name": "Transmission Fluid", "category": "transmission_fluid",
                      "description": "ATF for automatic/manual transmissions.", "brand": "SCA"},
    "wheels": {"name": "Tyres", "category": "tyres",
               "description": "All-season passenger tyre.", "brand": "SCA"},
    "suspension": {"name": "Shock Absorbers", "category": "shock_absorbers",
                   "description": "Standard replacement shock absorber.", "brand": "SCA"},
    "steering": {"name": "Steering Rack Boot", "category": "steering",
                 "description": "Steering rack protective boot.", "brand": "SCA"},
    "wipers": {"name": "Windshield Wiper Blades", "category": "wipers",
               "description": "Standard wiper blade refill pair.", "brand": "SCA"},
    "climate": {"name": "Cabin Air Filter", "category": "cabin_filter",
                "description": "Replacement cabin air filter.", "brand": "SCA"},
    "belts": {"name": "Drive Belts", "category": "belts",
              "description": "Serpentine/alternator drive belts.", "brand": "SCA"},
    "gaskets": {"name": "Gaskets & Seals", "category": "gaskets",
                "description": "Engine gasket and seal kit.", "brand": "SCA"},
    "body": {"name": "Body Clips & Fasteners", "category": "body_kits",
             "description": "Body panel clips and fasteners.", "brand": "SCA"},
    "exhaust": {"name": "Exhaust System", "category": "exhaust",
                "description": "Standard replacement exhaust components.", "brand": "SCA"},
    "performance": {"name": "Performance Parts", "category": "performance",
                    "description": "Performance upgrades and accessories.", "brand": "SCA"},
    "ignition": {"name": "Spark Plugs", "category": "spark_plugs",
                 "description": "Iridium spark plug set.", "brand": "NGK"},
    "electrical": {"name": "Battery", "category": "battery",
                   "description": "Lead-acid replacement battery.", "brand": "SCA"},
    "lighting": {"name": "Headlight Bulbs", "category": "lighting",
                 "description": "Halogen/LED replacement bulbs.", "brand": "SCA"},
    "tools": {"name": "Hand Tools", "category": "tools",
              "description": "General mechanic hand tools.", "brand": "SCA"},
    "marine": {"name": "Marine Parts", "category": "marine",
               "description": "Marine-grade parts and accessories.", "brand": "SCA"},
    "motorcycle": {"name": "Motorcycle Parts", "category": "motorcycle",
                   "description": "Motorcycle-specific parts and accessories.", "brand": "SCA"},
    "manuals": {"name": "Workshop Manuals", "category": "manuals",
                "description": "Vehicle service and repair manuals.", "brand": "Haynes"},
}

_SERVICE_GROUP_BY_TYPE = {v["category"]: k for k, v in _SCA_FALLBACK_PARTS.items()}

# Maps frontend service_type values -> the SCA inventory categories that satisfy
# that service. Used when prefilling an AI suggested service with parts.
_SERVICE_TYPE_TO_CATEGORIES = {
    "scheduled": ["engine", "fuel", "belts", "cooling"],
    "oil": ["engine", "belts"],
    "oil_change": ["engine", "belts"],
    "brake_pads": ["brakes"],
    "brake_fluid": ["brakes", "cooling"],
    "coolant": ["cooling", "gaskets"],
    "air_filter": ["climate"],
    "cabin_filter": ["climate"],
    "spark_plugs": ["spark_plugs", "ignition"],
    "transmission": ["transmission", "belts"],
    "timing_belt": ["belts", "gaskets", "engine"],
    "tyres": ["wheels"],
    "battery": ["electrical"],
}


def format_vehicle_str(vehicle: dict | None) -> str:
    if not vehicle:
        return "the vehicle"
    make = vehicle.get("make") or ""
    model = vehicle.get("model") or ""
    year = vehicle.get("year")
    parts = [p for p in (make, model) if p]
    label = " ".join(parts) or "vehicle"
    if year:
        label = f"{year} {label}".strip()
    return label


def build_inventory_from_categories(categories: list[dict], vehicle: dict | None = None) -> list[dict]:
    """Map raw SCA categories -> Inventory-formatted part suggestions.

    Each output item matches the backend Part schema shape so it can be
    created directly as a Part or presented to the user to add.
    """
    results: list[dict] = []
    seen = set()
    vehicle_str = format_vehicle_str(vehicle)
    for cat in categories:
        part_category = cat.get("part_category", "other")
        base = _SCA_FALLBACK_PARTS.get(part_category)
        if base is None:
            base = {
                "name": cat.get("name", part_category).title(),
                "category": part_category,
                "description": f"{vehicle_str} compatible {part_category.replace('_', ' ')}.",
                "brand": "SCA",
            }
        slug = cat.get("slug", part_category)
        if slug in seen:
            continue
        seen.add(slug)
        results.append({
            "name": base["name"],
            "category": base["category"],
            "description": base["description"],
            "brand": base["brand"],
            "supplier": "Supercheap Auto",
            "sku": cat.get("url", "").rsplit("/", 1)[-1] or f"sca-{slug}",
            "source": "supercheap",
            "url": cat.get("url", ""),
            "service_group": cat.get("service_group",
                                     _SERVICE_GROUP_BY_TYPE.get(part_category, "Other")),
            "min_quantity": 1,
            "unit_cost": 0.0,
            "quantity": 0,
        })
    return results


def suggest_parts_for_service(service_type: str, inventory_parts: list[dict],
                              sca_parts: list[dict]) -> list[dict]:
    """Prefill parts for an AI-suggested service.

    Preference order per the feature spec:
      1. Parts already in the user's inventory whose category matches the
         service, in stock first.
      2. SCA parts-guide suggestions matching the service, marked
         ``source: supercheap`` so the UI can label them "suggested from SCA".
    """
    wanted = set(_SERVICE_TYPE_TO_CATEGORIES.get(service_type, []))
    # normalise service_type (oil_change -> oil)
    if not wanted:
        want_type = service_type.replace("oil_change", "oil")
        wanted = set(_SERVICE_TYPE_TO_CATEGORIES.get(want_type, []))

    prefilled: list[dict] = []
    seen = set()

    def add(part: dict):
        key = part.get("sku") or part.get("name")
        if key in seen:
            return
        seen.add(key)
        prefilled.append(part)

    in_stock = [p for p in inventory_parts
                if p.get("service_group") or _category_to_sca_cat(p.get("category")) in wanted
                or _category_to_sca_cat(p.get("category")) in wanted
                or p.get("category") in wanted]
    for p in in_stock:
        if p.get("quantity", 0) > 0:
            add(p)
    for p in in_stock:
        if p.get("quantity", 0) <= 0:
            add(p)

    for p in sca_parts:
        cat = p.get("category", "")
        if cat in wanted or p.get("service_group") in [
                c for c in _SERVICE_GROUP_BY_TYPE if c in wanted]:
            add(p)

    return prefilled


def _category_to_sca_cat(category: str) -> str:
    category = (category or "").strip()
    cat_to_sca = {v["category"]: k for k, v in _SCA_FALLBACK_PARTS.items()}
    return cat_to_sca.get(category, category)
