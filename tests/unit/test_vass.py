"""Unit tests for the VASS deterministic rule engine."""

from backend.app.services.vass import (
    lookup_vehicle,
    decode_vin,
    generate_checklist,
    aggregate_results,
    _vkey,
    _VEHICLES,
    _CHECKLISTS,
)


def setup_module():
    """Clear caches before tests."""
    _VEHICLES.clear()
    _CHECKLISTS.clear()
    from backend.app.services.vass import _seed
    _seed()


def test_lookup_vehicle_known_combinations():
    """Test 5 known mod+vehicle-class combos for vehicle lookup."""
    # Combo 1: Toyota Hilux 2020 - compliant
    v = lookup_vehicle("Toyota", "Hilux", 2020)
    assert v is not None
    assert v.base_vehicle_id == "BV001"
    assert v.compliance_status == "compliant"

    # Combo 2: Ford Ranger 2019 - needs_review
    v = lookup_vehicle("Ford", "Ranger", 2019)
    assert v is not None
    assert v.base_vehicle_id == "BV002"
    assert v.compliance_status == "needs_review"

    # Combo 3: Unknown make/model/year
    v = lookup_vehicle("Unknown", "Model", 2025)
    assert v is None

    # Combo 4: Case insensitive lookup
    v = lookup_vehicle("toyota", "hilux", 2020)
    assert v is not None
    assert v.base_vehicle_id == "BV001"

    # Combo 5: Wrong year
    v = lookup_vehicle("Toyota", "Hilux", 2019)
    assert v is None


def test_decode_vin_rule_types():
    """Test VIN decoding covers all rule types."""
    # Rule type 1: Valid Toyota VIN
    info = decode_vin("MR0ABC12345678901")
    assert info.valid is True
    assert info.make == "Toyota"
    assert info.model == "Hilux"
    assert info.year == 2020
    assert info.body_style == "Ute"
    assert info.engine == "2.8D"
    assert info.country == "TH"

    # Rule type 2: Valid Ford VIN
    info = decode_vin("1FTXYZ12345678901")
    assert info.valid is True
    assert info.make == "Ford"
    assert info.model == "Ranger"
    assert info.year == 2019
    assert info.body_style == "Ute"
    assert info.engine == "2.0T"
    assert info.country == "US"

    # Rule type 3: Invalid length
    info = decode_vin("SHORT")
    assert info.valid is False
    assert "VIN must be 17 characters" in info.errors

    # Rule type 4: Invalid characters
    info = decode_vin("!@#ABC12345678901")
    assert info.valid is False
    assert "Invalid VIN characters" in info.errors

    # Rule type 5: Unknown prefix (valid structure, unknown make/model)
    info = decode_vin("ZZZABC12345678901")
    assert info.valid is True
    assert info.make is None
    assert info.model is None


def test_generate_checklist_mod_vehicle_combos():
    """Test 5 known mod+vehicle-class combos for checklist generation."""
    # Combo 1: Toyota Hilux BV001 - no modifications (base rules)
    items = generate_checklist("BV001", [])
    assert len(items) == 3
    categories = {i.category for i in items}
    assert categories == {"Lighting", "Brakes", "Emissions"}
    assert all(i.required for i in items)
    assert all(i.status == "pending" for i in items)

    # Combo 2: Toyota Hilux BV001 - exhaust modification
    items = generate_checklist("BV001", ["exhaust"])
    assert len(items) == 4  # base 3 + exhaust
    categories = {i.category for i in items}
    assert "Exhaust" in categories
    exhaust_item = next(i for i in items if i.category == "Exhaust")
    assert exhaust_item.description == "Exhaust modification compliance"

    # Combo 3: Toyota Hilux BV001 - engine modification
    items = generate_checklist("BV001", ["engine"])
    assert len(items) == 4  # base 3 + engine
    categories = {i.category for i in items}
    assert "Engine" in categories
    engine_item = next(i for i in items if i.category == "Engine")
    assert engine_item.description == "Engine modification compliance"

    # Combo 4: Ford Ranger BV002 - no modifications
    items = generate_checklist("BV002", [])
    assert len(items) == 3
    categories = {i.category for i in items}
    assert categories == {"Lighting", "Brakes", "Emissions"}

    # Combo 5: Ford Ranger BV002 - multiple modifications (exhaust + engine)
    items = generate_checklist("BV002", ["exhaust", "engine"])
    assert len(items) == 5  # base 3 + exhaust + engine
    categories = {i.category for i in items}
    assert "Exhaust" in categories
    assert "Engine" in categories


def test_generate_checklist_modification_case_insensitive():
    """Test modifications are case insensitive."""
    items = generate_checklist("BV001", ["EXHAUST", "Engine"])
    categories = {i.category for i in items}
    assert "Exhaust" in categories
    assert "Engine" in categories


def test_aggregate_results_pass_fail_outcomes():
    """Test aggregate_results with correct pass/fail outcomes."""
    # All pass -> compliant
    results = [
        {"item_id": "ch001", "status": "pass", "notes": "OK"},
        {"item_id": "ch002", "status": "pass", "notes": "OK"},
        {"item_id": "ch003", "status": "pass", "notes": "OK"},
    ]
    res = aggregate_results("BV001", results)
    assert res.overall_status == "compliant"
    assert res.passed == 3
    assert res.failed == 0
    assert res.score == 100.0

    # Some fail -> non_compliant
    results = [
        {"item_id": "ch001", "status": "pass", "notes": "OK"},
        {"item_id": "ch002", "status": "fail", "notes": "Failed"},
        {"item_id": "ch003", "status": "pass", "notes": "OK"},
    ]
    res = aggregate_results("BV001", results)
    assert res.overall_status == "non_compliant"
    assert res.passed == 2
    assert res.failed == 1
    assert res.score == 66.67

    # All fail -> non_compliant
    results = [
        {"item_id": "ch001", "status": "fail", "notes": "Failed"},
        {"item_id": "ch002", "status": "fail", "notes": "Failed"},
    ]
    res = aggregate_results("BV001", results)
    assert res.overall_status == "non_compliant"
    assert res.passed == 0
    assert res.failed == 2
    assert res.score == 0.0

    # Empty results -> pending
    results = []
    res = aggregate_results("BV001", results)
    assert res.overall_status == "pending"
    assert res.passed == 0
    assert res.failed == 0
    assert res.score == 0.0

    # Mixed statuses including pending
    results = [
        {"item_id": "ch001", "status": "pass", "notes": "OK"},
        {"item_id": "ch002", "status": "pending", "notes": "Not checked"},
        {"item_id": "ch003", "status": "fail", "notes": "Failed"},
    ]
    res = aggregate_results("BV001", results)
    assert res.overall_status == "non_compliant"  # fail takes precedence
    assert res.passed == 1
    assert res.failed == 1
    assert res.total == 3


def test_vkey_generation():
    """Test internal _vkey function."""
    key = _vkey("Toyota", "Hilux", 2020)
    assert key == "toyota|hilux|2020"

    key = _vkey("FORD", "RANGER", 2019)
    assert key == "ford|ranger|2019"


def test_checklist_storage_and_retrieval():
    """Test that checklists are stored and retrievable."""
    items = generate_checklist("BV001", ["exhaust"])
    assert "BV001" in _CHECKLISTS
    assert len(_CHECKLISTS["BV001"]) == 4

    # Generate again without modifications - should overwrite
    generate_checklist("BV001", [])
    assert len(_CHECKLISTS["BV001"]) == 3