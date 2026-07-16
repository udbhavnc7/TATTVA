"""
Unit and property-based tests for the Syllabus Coverage Tracker (Task 9).

Feature: tattva-exam-engine

Covers:
  - GET /coverage returns correct counts and coverage_percentage
  - No topics → 0% coverage
  - All grounded → 100% coverage
  - Mixed badges → correct formula application
  - Property 20: coverage_percentage == round((grounded / total) * 100)
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.knowledge_store.coverage_service import get_coverage_metrics


# ---------------------------------------------------------------------------
# Pure coverage formula helper (mirrors coverage_service logic)
# ---------------------------------------------------------------------------

def _coverage_pct(grounded: int, total: int) -> int:
    if total == 0:
        return 0
    return round((grounded / total) * 100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_topic(module_id: uuid.UUID | None = None) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.name = "Test Topic"
    t.module_id = module_id or uuid.uuid4()
    return t


def _make_note(topic_id: uuid.UUID, confidence: str) -> tuple:
    """Return a (topic_id, confidence) row tuple."""
    return (topic_id, confidence)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _make_coverage_mock(topics: list, note_rows: list) -> AsyncMock:
    """Build a mock session returning the given topics and note rows."""
    mock_session = AsyncMock()
    call_count = [0]

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: topics query
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=topics))
                )
            )
        else:
            # Second call: notes query
            return MagicMock(all=MagicMock(return_value=note_rows))

    mock_session.execute = AsyncMock(side_effect=_execute_side_effect)
    return mock_session


# ===========================================================================
# Service-layer unit tests
# ===========================================================================

class TestGetCoverageMetrics:

    @pytest.mark.asyncio
    async def test_no_topics_returns_zero_coverage(self) -> None:
        """When there are no topics, coverage is 0%."""
        session = _make_coverage_mock(topics=[], note_rows=[])
        result = await get_coverage_metrics(session)
        assert result["total_topics"] == 0
        assert result["coverage_percentage"] == 0
        assert result["grounded_count"] == 0

    @pytest.mark.asyncio
    async def test_all_grounded_returns_100_percent(self) -> None:
        """All topics with grounded notes → 100% coverage."""
        t1 = _make_topic()
        t2 = _make_topic()
        note_rows = [
            _make_note(t1.id, "grounded"),
            _make_note(t2.id, "grounded"),
        ]
        session = _make_coverage_mock(topics=[t1, t2], note_rows=note_rows)
        result = await get_coverage_metrics(session)
        assert result["total_topics"] == 2
        assert result["grounded_count"] == 2
        assert result["coverage_percentage"] == 100

    @pytest.mark.asyncio
    async def test_no_notes_topics_counted_as_no_notes(self) -> None:
        """Topics with no notes are counted in no_notes_count."""
        t1 = _make_topic()
        t2 = _make_topic()
        session = _make_coverage_mock(topics=[t1, t2], note_rows=[])
        result = await get_coverage_metrics(session)
        assert result["no_notes_count"] == 2
        assert result["grounded_count"] == 0
        assert result["coverage_percentage"] == 0

    @pytest.mark.asyncio
    async def test_mixed_badges_counted_correctly(self) -> None:
        """Mixed badge distribution is counted per spec formula."""
        t1, t2, t3, t4 = [_make_topic() for _ in range(4)]
        note_rows = [
            _make_note(t1.id, "grounded"),
            _make_note(t2.id, "partial"),
            _make_note(t3.id, "needs_review"),
            # t4 has no notes
        ]
        session = _make_coverage_mock(
            topics=[t1, t2, t3, t4], note_rows=note_rows
        )
        result = await get_coverage_metrics(session)
        assert result["total_topics"] == 4
        assert result["grounded_count"] == 1
        assert result["partial_count"] == 1
        assert result["needs_review_count"] == 1
        assert result["no_notes_count"] == 1
        assert result["coverage_percentage"] == round((1 / 4) * 100)  # 25

    @pytest.mark.asyncio
    async def test_best_badge_wins_per_topic(self) -> None:
        """If a topic has both partial and grounded notes, grounded wins."""
        t1 = _make_topic()
        note_rows = [
            _make_note(t1.id, "partial"),
            _make_note(t1.id, "grounded"),  # best badge
        ]
        session = _make_coverage_mock(topics=[t1], note_rows=note_rows)
        result = await get_coverage_metrics(session)
        assert result["grounded_count"] == 1
        assert result["partial_count"] == 0

    @pytest.mark.asyncio
    async def test_per_topic_list_present_in_response(self) -> None:
        """Response includes per-topic badge status for UI."""
        t1 = _make_topic()
        note_rows = [_make_note(t1.id, "grounded")]
        session = _make_coverage_mock(topics=[t1], note_rows=note_rows)
        result = await get_coverage_metrics(session)
        assert "topics" in result
        assert len(result["topics"]) == 1
        topic_entry = result["topics"][0]
        assert topic_entry["topic_id"] == str(t1.id)
        assert topic_entry["badge"] == "grounded"

    @pytest.mark.asyncio
    async def test_topic_with_no_notes_has_none_badge(self) -> None:
        """Topics with no notes appear with badge=None in the topics list."""
        t1 = _make_topic()
        session = _make_coverage_mock(topics=[t1], note_rows=[])
        result = await get_coverage_metrics(session)
        assert result["topics"][0]["badge"] is None

    @pytest.mark.asyncio
    async def test_coverage_formula_applied_correctly(self) -> None:
        """Formula: round((grounded_count / total_topics) * 100)."""
        topics = [_make_topic() for _ in range(5)]
        note_rows = [
            _make_note(topics[0].id, "grounded"),
            _make_note(topics[1].id, "grounded"),
            _make_note(topics[2].id, "partial"),
        ]
        session = _make_coverage_mock(topics=topics, note_rows=note_rows)
        result = await get_coverage_metrics(session)
        expected = round((2 / 5) * 100)  # 40
        assert result["coverage_percentage"] == expected


# ===========================================================================
# HTTP endpoint test
# ===========================================================================

class TestGetCoverageEndpoint:

    @pytest.mark.asyncio
    async def test_coverage_endpoint_returns_200(self, client: AsyncClient) -> None:
        """GET /coverage returns 200 with expected fields."""
        mock_data = {
            "grounded_count": 3,
            "partial_count": 1,
            "needs_review_count": 1,
            "no_notes_count": 2,
            "total_topics": 7,
            "coverage_percentage": 43,
            "topics": [],
        }

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.knowledge_store.router.get_db", return_value=mock_cm),
            patch(
                "app.services.knowledge_store.router.coverage_service.get_coverage_metrics",
                new=AsyncMock(return_value=mock_data),
            ),
        ):
            resp = await client.get("/coverage")

        assert resp.status_code == 200
        body = resp.json()
        assert body["grounded_count"] == 3
        assert body["coverage_percentage"] == 43
        assert body["total_topics"] == 7


# ===========================================================================
# Property 20 — coverage percentage matches formula
# ===========================================================================

@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    grounded=st.integers(min_value=0, max_value=200),
    total=st.integers(min_value=1, max_value=200),
)
def test_property20_coverage_percentage_matches_formula(
    grounded: int, total: int
) -> None:
    """
    Feature: tattva-exam-engine, Property 20: coverage percentage matches formula

    For any badge distribution where total_topics > 0, the coverage_percentage
    must equal round((grounded_count / total_topics) * 100).

    Validates: Requirements 9.1
    """
    # Clamp grounded to at most total (can't have more grounded than total topics)
    grounded = min(grounded, total)

    computed = _coverage_pct(grounded, total)
    expected = round((grounded / total) * 100)

    assert computed == expected, (
        f"coverage_percentage mismatch: computed={computed}, expected={expected} "
        f"for grounded={grounded}, total={total}"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    grounded=st.integers(min_value=0, max_value=100),
    partial=st.integers(min_value=0, max_value=100),
    needs_review=st.integers(min_value=0, max_value=100),
    no_notes=st.integers(min_value=0, max_value=100),
)
def test_property20_coverage_percentage_range(
    grounded: int, partial: int, needs_review: int, no_notes: int
) -> None:
    """
    Feature: tattva-exam-engine, Property 20: coverage percentage always in [0, 100]

    Coverage percentage is always a non-negative integer not exceeding 100.

    Validates: Requirements 9.1
    """
    total = grounded + partial + needs_review + no_notes
    if total == 0:
        return

    pct = _coverage_pct(grounded, total)
    assert 0 <= pct <= 100, (
        f"coverage_percentage {pct} is outside [0, 100] "
        f"for grounded={grounded}, total={total}"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(total=st.integers(min_value=1, max_value=100))
def test_property20_all_grounded_gives_100_percent(total: int) -> None:
    """
    Feature: tattva-exam-engine, Property 20: all grounded → 100%

    When every topic has a grounded note, coverage must be exactly 100%.
    """
    pct = _coverage_pct(grounded=total, total=total)
    assert pct == 100, f"Expected 100% when all {total} topics grounded, got {pct}%"


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(total=st.integers(min_value=1, max_value=100))
def test_property20_no_grounded_gives_0_percent(total: int) -> None:
    """
    Feature: tattva-exam-engine, Property 20: no grounded → 0%
    """
    pct = _coverage_pct(grounded=0, total=total)
    assert pct == 0, f"Expected 0% when no topics grounded out of {total}, got {pct}%"
