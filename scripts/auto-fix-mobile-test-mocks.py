#!/usr/bin/env python3
"""Auto-fix mobile test mock method signatures to match the current ApiClient interface.

When ApiClient method signatures change (e.g. adding an optional named parameter
to ``get``), mock classes in ``test/`` that ``extends ApiClient`` become invalid
overrides and cause ``flutter analyze`` to fail with ``invalid_override``
errors, blocking the sync-mobile workflow.  This script reads the current
ApiClient public method signatures from ``lib/core/api_client.dart`` and aligns
every mock override so analyze stays green.

Run from sync-mobile.sh after syncing frontend/lib:
    python3 scripts/auto-fix-mobile-test-mocks.py <mobile_dir>

Run standalone if the file path or ApiClient location differs:
    python3 scripts/auto-fix-mobile-test-mocks.py <mobile_dir> <api_client_path>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def extract_api_client_methods(api_client_path: Path) -> dict[str, str]:
    """Extract public method parameter-lists from the ApiClient class.

    Returns: ``{method_name: params_string}`` e.g.
    ``{"get": "String path, {Map<String, String>? query}"}``.
    """
    content = api_client_path.read_text()

    # Locate the ApiClient class body.
    class_match = re.search(r'class\s+ApiClient\s*\{', content)
    if not class_match:
        print(f"Warning: ApiClient class not found in {api_client_path}", file=sys.stderr)
        return {}

    body = content[class_match.end():]
    # The class opening '{' was consumed by the regex, so start depth at 1.
    depth = 1
    class_end = len(body)
    for i, ch in enumerate(body):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                class_end = i
                break
    body = body[:class_end]

    methods: dict[str, str] = {}

    # Match: Future<returnType> methodName(
    pat = re.compile(r'Future<[\w<>]+?>\s+(\w+)\s*\(', re.DOTALL)

    for m in pat.finditer(body):
        method_name = m.group(1)
        if method_name.startswith('_'):
            continue  # skip private methods / _send, _raw, _refresh

        # Walk forward to find the matching closing paren for the argument list.
        i = m.end() - 1  # position of '('
        depth = 0
        params = ""
        for j in range(i, len(body)):
            if body[j] == '(':
                depth += 1
            elif body[j] == ')':
                depth -= 1
                if depth == 0:
                    params = body[i + 1:j].strip()
                    break

        if params:
            methods[method_name] = params

    return methods


def fix_test_mocks(test_dir: Path, methods: dict[str, str]) -> int:
    """Fix mock method signatures in test files to match ApiClient interface.

    Returns: number of fixes applied.
    """
    if not test_dir.exists():
        return 0

    fixes = 0

    for test_file in sorted(test_dir.glob("**/*.dart")):
        content = test_file.read_text()

        if 'extends ApiClient' not in content:
            continue

        original = content

        for method_name, correct_params in methods.items():
            # Find method overrides: Future<returnType> methodName(params) [async] [{|=>]
            # Capture the param list so we can compare and replace.
            override_pat = re.compile(
                rf'(\bFuture<[\w<>]+?>\s+{method_name}\s*\()([\s\S]*?)(\))',
            )

            def _replacer(m: re.Match, cp: str = correct_params) -> str:
                nonlocal fixes
                current_params = re.sub(r'\s+', ' ', m.group(2).strip())
                correct_normalized = re.sub(r'\s+', ' ', cp.strip())
                if current_params != correct_normalized:
                    fixes += 1
                    return m.group(1) + cp + m.group(3)
                return m.group(0)

            content = override_pat.sub(_replacer, content)

        if content != original:
            test_file.write_text(content)
            print(f"  Fixed mock signatures in {test_file.name}")

    return fixes


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <mobile_dir> [api_client_path]", file=sys.stderr)
        sys.exit(1)

    mobile_dir = Path(sys.argv[1])

    if len(sys.argv) >= 3:
        api_client_path = Path(sys.argv[2])
    else:
        api_client_path = mobile_dir / "lib" / "core" / "api_client.dart"

    if not api_client_path.exists():
        print(f"Warning: {api_client_path} not found", file=sys.stderr)
        sys.exit(0)

    methods = extract_api_client_methods(api_client_path)

    if not methods:
        print("Warning: no public methods found in ApiClient", file=sys.stderr)
        sys.exit(0)

    print(f"==> ApiClient methods: {', '.join(sorted(methods.keys()))}")

    test_dir = mobile_dir / "test"
    fixes = fix_test_mocks(test_dir, methods)

    if fixes > 0:
        print(f"==> Fixed {fixes} mock method signature(s) in test files")
    else:
        print("==> No mock signature fixes needed — test mocks already match ApiClient interface")


if __name__ == "__main__":
    main()
