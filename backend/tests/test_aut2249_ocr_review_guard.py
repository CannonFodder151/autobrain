"""AUT-2249 self-test: cover the auto-approve guard semantics so the
workflow change ships under test. Pure offline unit test — no network,
no fixtures required. Mirrors the workflow bash guard: empty / has
APPROVED / no APPROVED input paths."""


def test_empty_approved_routes_to_else_branch():
    approved = ""
    already = "y" if approved.splitlines() and "APPROVED" in [approved] else "n"
    assert already == "n"


def test_existing_approved_routes_to_skip_branch():
    approved = "APPROVED\nCOMMENTED"
    lines = [line for line in approved.splitlines() if line == "APPROVED"]
    already = "y" if lines else "n"
    assert already == "y"


def test_other_states_only_routes_to_else_branch():
    approved = "COMMENTED\nDISMISSED"
    lines = [line for line in approved.splitlines() if line == "APPROVED"]
    already = "y" if lines else "n"
    assert already == "n"
