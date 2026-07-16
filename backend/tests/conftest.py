"""
Pytest configuration and shared fixtures for the Tattva Exam Engine test suite.
"""

from collections.abc import AsyncGenerator

import pytest
from hypothesis import HealthCheck, settings

# ---------------------------------------------------------------------------
# Hypothesis settings
# ---------------------------------------------------------------------------
# Register and load the "ci" profile so every property test runs
# max_examples=100 with the suppress_health_check for DB-less stubs.
settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")


# ---------------------------------------------------------------------------
# Database fixture (stub — yields None until a real test DB is wired up)
# ---------------------------------------------------------------------------
@pytest.fixture
async def db_session() -> AsyncGenerator[None, None]:
    """
    Async database session fixture.

    Currently a stub that yields None.  Replace the body with a real
    SQLAlchemy AsyncSession when integration tests are written.
    """
    yield None
