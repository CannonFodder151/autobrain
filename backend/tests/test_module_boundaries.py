"""Domain-module boundary guard (AUT-3814, Workstream D).

Each ``app/modules/<domain>/`` package is a self-contained vertical slice
layered as ``models`` -> ``schemas`` -> ``services`` -> ``api``. This guard
asserts those layers never reach upward, and that domains never import each
other.

Runs offline — pure AST walk of the source tree, no DB, no app settings, no
import-linter dependency — so it can run in the same CI job as the other
regression guards without pulling in the whole app import graph.
"""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
MODULES_DIR = APP_DIR / "modules"

# Lower layers may import from strictly lower layers; nothing reaches upward.
LAYERS = ("models", "schemas", "services", "api")


def _domain_dirs() -> list[Path]:
    return sorted(d for d in MODULES_DIR.iterdir() if d.is_dir() and (d / "__init__.py").exists())


def _imported_modules(source: str) -> set[str]:
    """Fully-qualified modules imported by a source file (imports + from-imports)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_domain_modules_exist() -> None:
    """The vehicles domain must exist — this guard is not vacuous."""
    domains = [d.name for d in _domain_dirs()]
    assert "vehicles" in domains, f"expected a vehicles domain module, found {domains}"


def test_no_upward_layer_imports() -> None:
    """A layer must not import from any layer above it."""
    violations: list[str] = []
    for domain in _domain_dirs():
        present = [layer for layer in LAYERS if (domain / layer).is_dir()]
        for layer in present:
            ceiling = present.index(layer)
            for py in sorted((domain / layer).rglob("*.py")):
                for imported in _imported_modules(py.read_text()):
                    parts = imported.split(".")
                    if len(parts) < 4 or parts[0] != "app" or parts[1] != "modules":
                        continue
                    if parts[2] != domain.name or parts[3] not in present:
                        continue
                    if present.index(parts[3]) > ceiling:
                        rel = py.relative_to(APP_DIR)
                        violations.append(f"{rel} imports upward: {imported}")
    assert not violations, "upward layer imports found:\n  " + "\n  ".join(violations)


def test_domains_do_not_import_each_other() -> None:
    """One domain must not reach into another's internals."""
    names = {d.name for d in _domain_dirs()}
    violations: list[str] = []
    for domain in _domain_dirs():
        for py in sorted(domain.rglob("*.py")):
            for imported in _imported_modules(py.read_text()):
                parts = imported.split(".")
                if len(parts) < 3 or parts[:2] != ["app", "modules"]:
                    continue
                if parts[2] != domain.name and parts[2] in names:
                    violations.append(
                        f"{py.relative_to(APP_DIR)} imports across domains: {imported}"
                    )
    assert not violations, "cross-domain imports found:\n  " + "\n  ".join(violations)


def test_domain_package_inits_do_not_import_api() -> None:
    """A domain's ``__init__`` must stay import-free.

    Eagerly importing the ``api`` layer from the package ``__init__`` drags
    ``app.api.deps`` into the module graph, which cycles back through
    ``app.models``. That cycle broke the first vehicles split (AUT-3814).
    """
    offenders: list[str] = []
    for domain in _domain_dirs():
        init = domain / "__init__.py"
        for imported in _imported_modules(init.read_text()):
            if imported.startswith("app.modules"):
                offenders.append(f"{init.relative_to(APP_DIR)} imports {imported}")
    assert not offenders, "domain __init__ files must not import sublayers:\n  " + "\n  ".join(
        offenders
    )


def test_legacy_paths_are_shims() -> None:
    """Old vehicle paths must re-export, not reimplement.

    Guards against a "copy instead of move" split silently forking the domain:
    the legacy path has to be a thin re-export of the module's own symbols.
    """
    pairs = {
        "models/vehicle.py": "app.modules.vehicles.models.vehicle",
        "schemas/vehicle.py": "app.modules.vehicles.schemas.vehicle",
        "services/rego.py": "app.modules.vehicles.services.rego",
        "services/odometer.py": "app.modules.vehicles.services.odometer",
        "services/ownership.py": "app.modules.vehicles.services.ownership",
        "services/vehicle.py": "app.modules.vehicles.services.vehicle",
        "api/v1/vehicles.py": "app.modules.vehicles.api.vehicles",
    }
    problems: list[str] = []
    for legacy, target in pairs.items():
        path = APP_DIR / legacy
        if not path.exists():
            problems.append(f"{legacy} was removed instead of kept as a shim")
            continue
        tree = ast.parse(path.read_text())
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(tree)):
            problems.append(f"{legacy} defines its own code; expected a re-export shim")
        if target not in _imported_modules(path.read_text()):
            problems.append(f"{legacy} does not re-export from {target}")
    assert not problems, "legacy vehicle paths are not thin shims:\n  " + "\n  ".join(problems)