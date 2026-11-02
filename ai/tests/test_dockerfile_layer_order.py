"""docker/backend/Dockerfile layer order guards (AUT-4979).

The Playwright browser download used to sit above the backend `pip install`, so
`python -m playwright install` ran against the bare `python:3.13` base and every
backend image build died with `No module named playwright`. Browsers must be
installed after the requirements that provide playwright, and the root/SUID
`chrome_sandbox` re-own must stay last so no later layer can mask it.
"""

from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "docker" / "backend" / "Dockerfile"


def _lines() -> list[str]:
    return DOCKERFILE.read_text().splitlines()


def _index_of(needle: str) -> int:
    for i, line in enumerate(_lines()):
        if needle in line:
            return i
    raise AssertionError(f"{needle!r} not found in {DOCKERFILE}")


def test_playwright_installed_after_requirements_and_before_suid_reown() -> None:
    requirements = _index_of("RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt")
    playwright = _index_of("python -m playwright install")
    suid = _index_of("chrome-sandbox -o -name chrome_sandbox")

    assert playwright > requirements, (
        "playwright install must run AFTER backend requirements are installed "
        "(playwright only exists in backend/requirements.txt)"
    )
    assert suid > playwright, (
        "the SUID chrome_sandbox re-own must stay the last root layer, after the "
        "browser install"
    )


def test_playwright_browsers_path_env_precedes_the_install() -> None:
    env = _index_of("ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright")
    install = _index_of("python -m playwright install")
    assert env < install, "PLAYWRIGHT_BROWSERS_PATH must be set before the browser download"