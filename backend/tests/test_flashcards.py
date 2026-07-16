"""
Unit tests for the Spaced Repetition Flashcard System (Task 12.6).

Covers:
  - recall_score=0  → repetitions reset to 0, interval=1
  - recall_score=5  → max ease_factor applied
  - recall_score=2  → ease_factor decreases (penalty)
  - next_review_at  → always strictly after now()
  - POST /flashcards/{id}/review with recall_score=-1 → 422
  - POST /flashcards/{id}/review with recall_score=6  → 422
  - GET /flashcards?due_only=true returns only due cards
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.generation.flashcard_service import update_sm2


# ---------------------------------------------------------------------------
# update_sm2 pure-function tests
# ---------------------------------------------------------------------------

class TestUpdateSm2:
    """Tests for the pure SM-2 update function."""

    def test_recall_0_resets_repetitions_and_interval(self) -> None:
        """recall_score=0 → repetitions=0, interval_days=1 (failed recall)."""
        result = update_sm2(ease_factor=2.5, interval_days=10, repetitions=5, recall_score=0)
        assert result["repetitions"] == 0
        assert result["interval_days"] == 1

    def test_recall_1_resets(self) -> None:
        """recall_score=1 < 3 → still a failed recall."""
        result = update_sm2(ease_factor=2.5, interval_days=6, repetitions=3, recall_score=1)
        assert result["repetitions"] == 0
        assert result["interval_days"] == 1

    def test_recall_2_resets(self) -> None:
        """recall_score=2 < 3 → failed recall."""
        result = update_sm2(ease_factor=2.5, interval_days=6, repetitions=3, recall_score=2)
        assert result["repetitions"] == 0
        assert result["interval_days"] == 1

    def test_recall_3_increments_repetitions(self) -> None:
        """recall_score=3 >= 3 → successful recall, repetitions incremented."""
        result = update_sm2(ease_factor=2.5, interval_days=1, repetitions=0, recall_score=3)
        assert result["repetitions"] == 1
        assert result["interval_days"] == 1

    def test_recall_3_second_rep_gives_6_day_interval(self) -> None:
        """Second successful recall → interval=6 days."""
        result = update_sm2(ease_factor=2.5, interval_days=1, repetitions=1, recall_score=3)
        assert result["repetitions"] == 2
        assert result["interval_days"] == 6

    def test_recall_3_third_rep_uses_ef_multiplier(self) -> None:
        """Third+ successful recall → interval = round(prev_interval * ef)."""
        result = update_sm2(ease_factor=2.5, interval_days=6, repetitions=2, recall_score=3)
        expected_interval = round(6 * 2.5)
        assert result["interval_days"] == expected_interval
        assert result["repetitions"] == 3

    def test_recall_5_increases_ease_factor(self) -> None:
        """recall_score=5 → ease_factor increases."""
        result = update_sm2(ease_factor=2.5, interval_days=1, repetitions=0, recall_score=5)
        expected_ef = 2.5 + (0.1 - (5 - 5) * (0.08 + (5 - 5) * 0.02))
        assert abs(result["ease_factor"] - expected_ef) < 0.001

    def test_recall_2_decreases_ease_factor(self) -> None:
        """recall_score=2 → ease_factor decreases (failure penalty)."""
        original_ef = 2.5
        result = update_sm2(ease_factor=original_ef, interval_days=6, repetitions=3, recall_score=2)
        new_ef = original_ef + (0.1 - (5 - 2) * (0.08 + (5 - 2) * 0.02))
        new_ef = max(1.3, new_ef)
        assert abs(result["ease_factor"] - new_ef) < 0.001

    def test_ease_factor_never_below_1_3(self) -> None:
        """ease_factor floor is always 1.3."""
        result = update_sm2(ease_factor=1.3, interval_days=1, repetitions=0, recall_score=0)
        assert result["ease_factor"] >= 1.3

    def test_recall_0_low_ef_stays_at_floor(self) -> None:
        """Even with a very low starting EF and failed recall, EF stays >= 1.3."""
        result = update_sm2(ease_factor=1.3, interval_days=5, repetitions=2, recall_score=0)
        assert result["ease_factor"] >= 1.3

    def test_next_review_at_is_in_future(self) -> None:
        """next_review_at must always be strictly after current time."""
        before = datetime.now(timezone.utc)
        result = update_sm2(ease_factor=2.5, interval_days=1, repetitions=0, recall_score=3)
        assert result["next_review_at"] > before

    def test_next_review_at_respects_interval(self) -> None:
        """next_review_at should be approximately interval_days from now."""
        result = update_sm2(ease_factor=2.5, interval_days=6, repetitions=2, recall_score=5)
        expected_interval = round(6 * 2.5)
        expected_date = datetime.now(timezone.utc) + timedelta(days=expected_interval)
        # Allow 5-second tolerance
        assert abs((result["next_review_at"] - expected_date).total_seconds()) < 5


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _make_flashcard_mock(
    card_id: uuid.UUID | None = None,
    ease_factor: float = 2.5,
    interval_days: int = 1,
    repetitions: int = 0,
) -> MagicMock:
    card = MagicMock()
    card.id = card_id or uuid.uuid4()
    card.ease_factor = ease_factor
    card.interval_days = interval_days
    card.repetitions = repetitions
    card.next_review_at = datetime.now(timezone.utc) + timedelta(days=interval_days)
    return card


class TestFlashcardReviewEndpoint:

    @pytest.mark.asyncio
    async def test_valid_recall_score_returns_200(self, client: AsyncClient) -> None:
        """POST /flashcards/{id}/review with valid recall_score returns 200."""
        card_id = uuid.uuid4()
        updated_card = _make_flashcard_mock(card_id=card_id, ease_factor=2.6, interval_days=1)

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.generation.router.get_db", return_value=mock_cm),
            patch(
                "app.services.generation.router.flashcard_service.submit_review",
                new=AsyncMock(return_value=updated_card),
            ),
        ):
            resp = await client.post(
                f"/flashcards/{card_id}/review",
                json={"recall_score": 5},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["flashcard_id"] == str(card_id)
        assert "ease_factor" in body
        assert "next_review_at" in body

    @pytest.mark.asyncio
    async def test_recall_score_minus_1_returns_422(self, client: AsyncClient) -> None:
        """recall_score=-1 must return 422."""
        card_id = uuid.uuid4()
        resp = await client.post(
            f"/flashcards/{card_id}/review",
            json={"recall_score": -1},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_recall_score_6_returns_422(self, client: AsyncClient) -> None:
        """recall_score=6 must return 422."""
        card_id = uuid.uuid4()
        resp = await client.post(
            f"/flashcards/{card_id}/review",
            json={"recall_score": 6},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_recall_score_boundary_0_is_valid(self, client: AsyncClient) -> None:
        """recall_score=0 is valid (boundary)."""
        card_id = uuid.uuid4()
        updated_card = _make_flashcard_mock(card_id=card_id)

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.generation.router.get_db", return_value=mock_cm),
            patch(
                "app.services.generation.router.flashcard_service.submit_review",
                new=AsyncMock(return_value=updated_card),
            ),
        ):
            resp = await client.post(
                f"/flashcards/{card_id}/review",
                json={"recall_score": 0},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_flashcard_not_found_returns_404(self, client: AsyncClient) -> None:
        """Non-existent flashcard returns 404."""
        card_id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.generation.router.get_db", return_value=mock_cm),
            patch(
                "app.services.generation.router.flashcard_service.submit_review",
                new=AsyncMock(side_effect=LookupError("not found")),
            ),
        ):
            resp = await client.post(
                f"/flashcards/{card_id}/review",
                json={"recall_score": 3},
            )

        assert resp.status_code == 404


class TestGetFlashcardsEndpoint:

    @pytest.mark.asyncio
    async def test_get_flashcards_returns_counts(self, client: AsyncClient) -> None:
        """GET /flashcards returns card_count and due_count."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.generation.router.get_db", return_value=mock_cm),
            patch(
                "app.services.generation.router.flashcard_service.get_flashcards",
                new=AsyncMock(return_value={"card_count": 10, "due_count": 4}),
            ),
        ):
            resp = await client.get("/flashcards")

        assert resp.status_code == 200
        body = resp.json()
        assert body["card_count"] == 10
        assert body["due_count"] == 4

    @pytest.mark.asyncio
    async def test_get_flashcards_due_only_filter(self, client: AsyncClient) -> None:
        """GET /flashcards?due_only=true passes filter correctly."""
        captured_args = {}

        async def _mock_get(session, topic_id=None, due_only=False):
            captured_args["due_only"] = due_only
            return {"card_count": 5, "due_count": 3}

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.generation.router.get_db", return_value=mock_cm),
            patch(
                "app.services.generation.router.flashcard_service.get_flashcards",
                new=_mock_get,
            ),
        ):
            resp = await client.get("/flashcards?due_only=true")

        assert resp.status_code == 200
        assert captured_args.get("due_only") is True
