"""Doc-schema drift guard for the Home Assistant integration (AUT-2543).

Validates that the paths and field names documented in
`docs/home-assistant-integration.md` and `docs/api-spec.md` match the real
HA route table and schemas.

Skips automatically if the HA code is not present (i.e. before AUT-2541's
PR merges). The doc changes in AUT-2543 ship on top of AUT-2541, so on
main the test should not block CI — it should guard against drift once the
code is live.
"""

import re
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# These paths are the ones declared by the HA router in
# `backend/app/api/v1/ha.py`. Keep this list in sync with the route table.
REAL_HA_PATHS = {
    "/ha/tokens",
    "/ha/tokens/{id}",
    "/ha/vehicles",
    "/ha/vehicles/{id}/service-intervals",
    "/ha/vehicles/{id}/analytics",
    "/ha/service-reminders",
}


def _doc_rest_paths() -> set[str]:
    doc = (ROOT / "docs" / "home-assistant-integration.md").read_text()
    raw = re.findall(r"/api/v1(/ha/[^\s`\"]+)", doc)
    paths = set()
    for p in raw:
        # Strip backtick/quotes that trail the matched path.
        p = p.strip().rstrip("'\"")
        # Normalise the documented placeholder used in code samples.
        p = p.replace("<VEHICLE_UUID>", "{id}")
        p = p.rstrip("/")
        paths.add(p)
    return paths


def _api_spec_ha_paths() -> set[str]:
    txt = (ROOT / "docs" / "api-spec.md").read_text()
    rows = re.findall(r"`/ha/[A-Za-z0-9_{}\[\]./:-]+`", txt)
    paths = set()
    for r in rows:
        p = r.strip("`")
        if p.startswith("/ha/"):
            paths.add(p)
    return paths


class TestHomeAssistantDocsPaths:
    """Validate documented paths don't contain the `ha/v1/` double-prefix bug
    from the draft PR-520 doc and that the path set matches the route table."""

    @staticmethod
    def test_no_double_prefix() -> None:
        doc = (ROOT / "docs" / "home-assistant-integration.md").read_text()
        assert "/api/v1/ha/v1/" not in doc, (
            "Draft PR-520 had `/api/v1/ha/v1/...` paths — remove the extra `v1` "
            "layer from all documented URLs."
        )

    def test_doc_paths_match_route_table(self) -> None:
        paths = _doc_rest_paths()
        assert paths, "No /api/v1/ha/* paths found in docs/home-assistant-integration.md"
        assert paths == REAL_HA_PATHS, (
            f"Documented HA paths differ from the actual route table.\n"
            f"In docs but not routes: {sorted(paths - REAL_HA_PATHS)}\n"
            f"In routes but not docs: {sorted(REAL_HA_PATHS - paths)}"
        )

    def test_api_spec_paths_match_route_table(self) -> None:
        paths = _api_spec_ha_paths()
        assert paths, "No /api/v1/ha/* paths found in docs/api-spec.md HA section"
        assert paths == REAL_HA_PATHS, (
            f"api-spec.md HA paths differ from the actual route table.\n"
            f"In spec but not routes: {sorted(paths - REAL_HA_PATHS)}\n"
            f"In routes but not spec: {sorted(REAL_HA_PATHS - paths)}"
        )


class TestHomeAssistantDocsFieldNames:
    """Validate the field names declared in the doc examples exist in the HA
    Pydantic schemas. Skips if the HA schemas haven't shipped yet."""

    _DOCUMENTED_ANALYTICS_FIELDS = {
        "fuel_total",
        "service_total",
        "total_cost_of_ownership",
        "cost_per_km",
        "total_km_tracked",
        "count_services",
        "vehicle_nickname",
        "vehicle_id",
    }

    _DOCUMENTED_REMINDER_FIELDS = {
        "vehicle_id",
        "vehicle_nickname",
        "service_type",
        "next_due_km",
        "next_due_date",
        "due_in_km",
        "days_until_due",
    }

    _DOCUMENTED_INTERVAL_FIELDS = {
        "id",
        "vehicle_nickname",
        "service_type",
        "next_due_km",
        "next_due_date",
        "status",
    }

    _DOCUMENTED_VEHICLE_FIELDS = {
        "id",
        "nickname",
        "rego",
        "make",
        "model",
        "year",
        "odometer_km",
        "fuel_type",
        "powertrain",
    }

    @staticmethod
    @pytest.mark.skipif(
        not (ROOT / "backend" / "app" / "schemas" / "ha.py").exists(),
        reason="HA schemas (AUT-2541) not yet shipped — test guards future drift",
    )
    def test_analytics_schema_fields_match_docs() -> None:
        from app.schemas.ha import HaAnalyticsOut  # noqa: PLC0415

        fields = set(HaAnalyticsOut.model_fields)
        missing = TestHomeAssistantDocsFieldNames._DOCUMENTED_ANALYTICS_FIELDS - fields
        assert not missing, f"Doc references fields not in HaAnalyticsOut: {sorted(missing)}"

    @staticmethod
    @pytest.mark.skipif(
        not (ROOT / "backend" / "app" / "schemas" / "ha.py").exists(),
        reason="HA schemas (AUT-2541) not yet shipped — test guards future drift",
    )
    def test_reminder_schema_fields_match_docs() -> None:
        from app.schemas.ha import HaServiceReminderOut  # noqa: PLC0415

        fields = set(HaServiceReminderOut.model_fields)
        missing = TestHomeAssistantDocsFieldNames._DOCUMENTED_REMINDER_FIELDS - fields
        assert not missing, f"Doc references fields not in HaServiceReminderOut: {sorted(missing)}"

    @staticmethod
    @pytest.mark.skipif(
        not (ROOT / "backend" / "app" / "schemas" / "ha.py").exists(),
        reason="HA schemas (AUT-2541) not yet shipped — test guards future drift",
    )
    def test_interval_schema_fields_match_docs() -> None:
        from app.schemas.ha import HaServiceIntervalOut  # noqa: PLC0415

        fields = set(HaServiceIntervalOut.model_fields)
        missing = TestHomeAssistantDocsFieldNames._DOCUMENTED_INTERVAL_FIELDS - fields
        assert not missing, f"Doc references fields not in HaServiceIntervalOut: {sorted(missing)}"

    @staticmethod
    @pytest.mark.skipif(
        not (ROOT / "backend" / "app" / "schemas" / "ha.py").exists(),
        reason="HA schemas (AUT-2541) not yet shipped — test guards future drift",
    )
    def test_vehicle_schema_fields_match_docs() -> None:
        from app.schemas.ha import HaVehicleOut  # noqa: PLC0415

        fields = set(HaVehicleOut.model_fields)
        missing = TestHomeAssistantDocsFieldNames._DOCUMENTED_VEHICLE_FIELDS - fields
        assert not missing, f"Doc references fields not in HaVehicleOut: {sorted(missing)}"
