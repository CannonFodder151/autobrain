"""The AI gateway must be importable under BOTH package names (AUT-2784).

`docker/backend/Dockerfile` copies `ai/app` to `ai_app` and runs it as a
co-process on :8001 inside the backend container, so the AI package has to be
self-contained. An absolute `from app.<x>` import in `ai/` silently resolves to
the BACKEND's `app` package in that image — which has no `logging`, `modules`,
`router_client` or `fallbacks` — and the gateway dies with
`ModuleNotFoundError: No module named 'app.logging'` at startup.

The standalone `ai/` test suite (which imports `app.main`) cannot catch that, so
this test simulates the image layout: backend `app` and AI `ai_app` side by side,
AI served by uvicorn on :8001.
"""

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AI_APP = REPO / "ai" / "app"
BACKEND_APP = REPO / "backend" / "app"


def _absolute_app_imports() -> list[tuple[str, int]]:
    """Every `from app.…` / `import app.…` statement in ai/, ignoring comments."""
    hits = []
    for path in sorted(AI_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app"):
                hits.append((str(path.relative_to(REPO)), node.lineno))
            elif isinstance(node, ast.Import):
                if any(a.name == "app" or a.name.startswith("app.") for a in node.names):
                    hits.append((str(path.relative_to(REPO)), node.lineno))
    return hits


def test_ai_package_uses_no_absolute_app_imports() -> None:
    """ai/ must import its siblings relatively, never via top-level `app`."""
    hits = _absolute_app_imports()
    assert not hits, (
        "absolute `app.*` imports in the AI gateway break the merged backend "
        "image (ai/app is copied to ai_app, where `app` resolves to the backend "
        f"package): {hits}"
    )


def test_ai_app_is_copied_as_ai_app_by_the_backend_image() -> None:
    """The Dockerfile must ship the gateway as `ai_app` and start it on :8001."""
    dockerfile = (REPO / "docker" / "backend" / "Dockerfile").read_text()
    assert "COPY ai/app ./ai_app" in dockerfile, "backend image no longer ships ai/ as ai_app"
    assert not re.search(r"^FROM .*ai/", dockerfile, re.M), (
        "the backend image must be the single build; a separate ai stage/base is out"
    )


def test_gateway_imports_in_the_merged_image_layout(tmp_path: Path) -> None:
    """Simulate the image: backend `app` + gateway `ai_app`, gateway must import."""
    img = tmp_path / "img"
    img.mkdir()
    shutil.copytree(BACKEND_APP, img / "app")
    shutil.copytree(AI_APP, img / "ai_app")

    code = "import sys; sys.path.insert(0, '.'); import ai_app.main as m; print(len(m.MODULES))"
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=img, capture_output=True, text=True, timeout=180
    )
    assert proc.returncode == 0, f"merged image layout fails to import:\n{proc.stderr}"
    assert int(proc.stdout.strip()) > 0


def test_gateway_serves_requests_in_the_merged_image_layout(tmp_path: Path) -> None:
    """End-to-end in the merged layout: :8001 answers /health and rejects bad keys."""
    img = tmp_path / "img"
    img.mkdir()
    shutil.copytree(BACKEND_APP, img / "app")
    shutil.copytree(AI_APP, img / "ai_app")

    code = """
import os, sys
os.environ['AI_GATEWAY_API_KEY'] = 'test-shared-key'
os.environ['AI_ROUTER_URL'] = 'http://placeholder:port'
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from ai_app.main import app
c = TestClient(app)
print(c.get('/health').status_code, c.post('/v1/parts-guide', json={}).status_code)
"""
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=img, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, f"merged gateway cannot serve:\n{proc.stderr}"
    # A transitive import logs a date on stdout; the result line is last.
    health, unauthorised = (int(x) for x in proc.stdout.strip().splitlines()[-1].split())
    assert health == 200, f"gateway /health returned {health} in the merged layout"
    assert unauthorised in (401, 422), (
        f"gateway auth/body validation did not engage in the merged layout: {unauthorised}"
    )
