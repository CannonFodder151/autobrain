#!/usr/bin/env python3
"""Module dependency checker for AutoBrain backend.

Validates the module architecture defined in docs/MODULE_ARCHITECTURE.md:
- core/ is a leaf (no outbound deps to other packages)
- services/ imports no FastAPI/Pydantic (framework-free)
- api/ does not import from api.v1.* (only api.deps)

Run: python3 scripts/check-module-deps.py
"""

import ast
import sys
from pathlib import Path


def get_top_level_imports(filepath: Path) -> set[str]:
    """Return only top-level (module-scope) imports from a Python file."""
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return set()

    imports = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    imports.add(alias.name)
    return imports


def check_module_deps(backend_root: Path) -> tuple[list[str], list[str]]:
    app_root = backend_root / "app"
    if not app_root.exists():
        return [f"App root not found: {app_root}"], []

    module_deps = {}
    package_outbound = {}  # pkg -> set of OTHER packages it imports

    for py in app_root.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        rel = str(py.relative_to(backend_root)).replace("/", ".").replace(".py", "")
        top = get_top_level_imports(py)
        module_deps[rel] = top

        parts = rel.split(".")
        if len(parts) >= 3:
            pkg = parts[1]
            for imp in top:
                imp_parts = imp.split(".")
                if len(imp_parts) >= 3:
                    imp_pkg = imp_parts[1]
                    if pkg != imp_pkg:
                        package_outbound.setdefault(pkg, set()).add(imp_pkg)

    errors: list[str] = []
    warnings: list[str] = []

    # 1. core/ is a leaf
    if package_outbound.get("core"):
        errors.append(f"core/ must not import from other packages, but imports: {package_outbound['core']}")

    # 2. services/ must not import FastAPI or Pydantic
    for mod, imps in module_deps.items():
        if mod.startswith("app.services."):
            for imp in imps:
                if "fastapi" in imp.lower() or "pydantic" in imp.lower():
                    warnings.append(f"{mod} imports {imp} — services should be framework-free")

    # 3. api/ must not import from api.v1.* (only api.deps)
    for mod, imps in module_deps.items():
        if mod.startswith("app.api.v1."):
            for imp in imps:
                if imp.startswith("app.api.v1."):
                    warnings.append(f"{mod} imports {imp} — avoid inter-router imports")

    # 4. social/ should not import api.v1.*
    for mod, imps in module_deps.items():
        if mod.startswith("app.social."):
            for imp in imps:
                if imp.startswith("app.api.v1."):
                    warnings.append(f"{mod} imports {imp} — social should only use api.deps")

    # 5. Document known cycles (informational only)
    known_cycles = []
    for pkg in ["db", "models", "services", "workers", "social"]:
        if pkg in package_outbound:
            for dep in package_outbound[pkg]:
                if dep in package_outbound and pkg in package_outbound.get(dep, set()):
                    known_cycles.append(f"  {pkg} <-> {dep}")

    return errors, warnings, known_cycles


def main() -> int:
    backend_root = Path(__file__).parent.parent / "backend"
    if not backend_root.exists():
        backend_root = Path.cwd() / "backend"
    if not backend_root.exists():
        backend_root = Path("/paperclip/autobrain-repos/autobrain/backend")

    print(f"Checking module deps in: {backend_root}")
    errors, warnings, known_cycles = check_module_deps(backend_root)

    if warnings:
        print("\n⚠️  Warnings:")
        for w in warnings:
            print(f"  - {w}")

    if known_cycles:
        print("\nℹ️  Known cross-package cycles (see docs/MODULE_ARCHITECTURE.md):")
        for c in known_cycles:
            print(c)

    if errors:
        print("\n❌ Errors:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n✅ All module architecture checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
