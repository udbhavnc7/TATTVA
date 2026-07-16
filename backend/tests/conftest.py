"""
Pytest configuration and shared fixtures for the Tattva Exam Engine test suite.
"""

from collections.abc import AsyncGenerator

import pytest
from hypothesis import HealthCheck, settings

# ---------------------------------------------------------------------------
# Hypothesis settings
# ---------------------------------------------------------------------------
# "fast" profile — used during local development for quick feedback.
# "ci"   profile — higher coverage for CI/CD pipelines.
settings.register_profile(
    "fast",
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
# Load "fast" by default so local runs finish quickly.
# Switch to "ci" by setting the HYPOTHESIS_PROFILE=ci env var or
# passing --hypothesis-profile=ci on the pytest command line.
settings.load_profile("fast")


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
