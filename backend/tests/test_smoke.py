"""
Smoke tests — confirm the FastAPI application can be imported and has routes.
"""

import pytest


@pytest.mark.unit
def test_app_imports() -> None:
    """The FastAPI app object is importable without errors."""
    from app.main import app  # noqa: PLC0415

    assert app is not None


@pytest.mark.unit
def test_app_has_routes() -> None:
    """The app has at least the root health-check route registered."""
    from app.main import app  # noqa: PLC0415

    routes = [r.path for r in app.routes]  # type: ignore[attr-defined]
    assert "/" in routes


@pytest.mark.unit
def test_app_title() -> None:
    """The app title matches the spec."""
    from app.main import app  # noqa: PLC0415

    assert app.title == "Tattva Exam Engine"
