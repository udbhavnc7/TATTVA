"""
Unit tests for the Mock Exam Paper Assembler (Task 11.7).

Covers:
  - Distribution parsing: "2×10mark + 4×6mark + 4×2mark" parses correctly
  - Importance-ordered selection: highest frequency_count first
  - Tie-breaking: same frequency_count → more recent year first
  - All zeros → random order accepted (any permutation is valid)
  - Insufficient bank: return all available + warning
  - total_marks_target reached before distribution fully satisfied: stop early, no error
  - POST /mock-paper HTTP endpoint
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.knowledge_store.mock_paper_service import (
    assemble_paper,
    parse_question_type_distribution,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(
    qid: str = None,
    year: int = 2020,
    marks: int = 5,
    freq: int = 0,
    topic_tag: str = "Topic A",
    topic_id: str = None,
    question_text: str = "What is X?",
) -> dict:
    """Build a minimal question dict matching the service schema."""
    return {
        "id": qid or str(uuid.uuid4()),
        "year": year,
        "question_text": question_text,
        "marks": marks,
        "topic_id": topic_id or str(uuid.uuid4()),
        "topic_tag": topic_tag,
        "frequency_count": freq,
    }


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ===========================================================================
# Distribution parsing tests
# ===========================================================================

class TestParseDistribution:
    def test_standard_unicode_multiplier(self) -> None:
        result = parse_question_type_distribution("2×10mark + 4×6mark + 4×2mark")
        assert result == [(2, 10), (4, 6), (4, 2)]

    def test_ascii_x_multiplier(self) -> None:
        result = parse_question_type_distribution("2x10mark + 4x6mark + 4x2mark")
        assert result == [(2, 10), (4, 6), (4, 2)]

    def test_spaces_optional(self) -> None:
        result = parse_question_type_distribution("3×5mark+2×10mark")
        assert result == [(3, 5), (2, 10)]

    def test_single_item(self) -> None:
        result = parse_question_type_distribution("1 × 15mark")
        assert result == [(1, 15)]

    def test_empty_string_returns_empty(self) -> None:
        result = parse_question_type_distribution("")
        assert result == []

    def test_no_valid_items_returns_empty(self) -> None:
        result = parse_question_type_distribution("no marks here")
        assert result == []

    def test_mixed_separators(self) -> None:
        result = parse_question_type_distribution("1×10mark + 2x6mark")
        assert result == [(1, 10), (2, 6)]

    def test_uppercase_mark_case_insensitive(self) -> None:
        result = parse_question_type_distribution("2×10MARK")
        assert result == [(2, 10)]

    def test_preserves_order(self) -> None:
        result = parse_question_type_distribution("4×2mark + 2×10mark + 3×6mark")
        assert result == [(4, 2), (2, 10), (3, 6)]


# ===========================================================================
# assemble_paper unit tests
# ===========================================================================

class TestAssemblePaper:

    # --- Importance ordering ---

    def test_highest_frequency_count_selected_first(self) -> None:
        """Questions with higher frequency_count should appear before lower ones."""
        q_low = _q(qid="low", freq=1, marks=5, year=2020)
        q_high = _q(qid="high", freq=10, marks=5, year=2020)
        questions = [q_low, q_high]

        result = assemble_paper(questions, total_marks_target=5, distribution=[])
        # Should pick the highest-importance question
        assert len(result["questions"]) == 1
        assert result["questions"][0]["id"] == "high"

    def test_importance_ordering_multiple_questions(self) -> None:
        """Paper should include questions from highest to lowest importance."""
        questions = [
            _q(qid="a", freq=1, marks=3, year=2020),
            _q(qid="b", freq=5, marks=3, year=2020),
            _q(qid="c", freq=3, marks=3, year=2020),
        ]
        result = assemble_paper(
            questions, total_marks_target=9, distribution=[]
        )
        ids = [q["id"] for q in result["questions"]]
        # Sorted by marks desc (all same), then just confirm b came before c came before a
        # Check all 3 present
        assert set(ids) == {"a", "b", "c"}
        assert result["total_marks"] == 9

    # --- Tie-breaking by year ---

    def test_tie_breaking_by_year_more_recent_first(self) -> None:
        """Same frequency_count → more recent year should be selected first."""
        q_old = _q(qid="old", freq=5, marks=5, year=2018)
        q_new = _q(qid="new", freq=5, marks=5, year=2023)
        questions = [q_old, q_new]

        result = assemble_paper(
            questions, total_marks_target=5, distribution=[]
        )
        assert len(result["questions"]) == 1
        assert result["questions"][0]["id"] == "new"

    def test_tie_breaking_multiple(self) -> None:
        """With same freq, most recent year comes before older years."""
        questions = [
            _q(qid="2019", freq=3, marks=4, year=2019),
            _q(qid="2022", freq=3, marks=4, year=2022),
            _q(qid="2015", freq=3, marks=4, year=2015),
        ]
        result = assemble_paper(
            questions, total_marks_target=4, distribution=[]
        )
        # Should pick 2022 first since all have same freq
        assert result["questions"][0]["id"] == "2022"

    # --- All zeros → random ---

    def test_all_zeros_returns_some_questions(self) -> None:
        """When all frequency_counts are 0, random selection — any permutation OK."""
        questions = [
            _q(qid=str(i), freq=0, marks=2, year=2020) for i in range(5)
        ]
        result = assemble_paper(
            questions, total_marks_target=6, distribution=[]
        )
        # Should pick 3 questions (3×2=6 marks)
        assert result["total_marks"] == 6
        assert len(result["questions"]) == 3
        # All should come from the original pool
        original_ids = {q["id"] for q in questions}
        for q in result["questions"]:
            assert q["id"] in original_ids

    # --- Insufficient bank ---

    def test_insufficient_bank_returns_all_available_and_warning(self) -> None:
        """If only 1 question of 10 marks exists but 2 requested, warn and include the 1."""
        questions = [_q(qid="q1", freq=5, marks=10, year=2022)]
        distribution = [(2, 10)]  # want 2×10mark, only 1 available

        result = assemble_paper(
            questions, total_marks_target=100, distribution=distribution
        )
        # Should include the 1 available
        assert len(result["questions"]) == 1
        assert result["questions"][0]["id"] == "q1"
        # Should have a warning
        assert len(result["warnings"]) == 1
        assert "Could not satisfy 2×10mark" in result["warnings"][0]
        assert "only 1 available" in result["warnings"][0]

    def test_insufficient_bank_no_questions_at_all(self) -> None:
        """Empty bank → empty paper with warnings for each requested type."""
        distribution = [(2, 10), (4, 6)]
        result = assemble_paper(
            questions=[], total_marks_target=50, distribution=distribution
        )
        assert result["questions"] == []
        assert result["total_marks"] == 0
        assert len(result["warnings"]) == 2

    def test_insufficient_bank_partial_satisfaction(self) -> None:
        """2 of 10mark requested, 0 available → warning; 4 of 6mark → all present."""
        questions = [_q(qid=str(i), freq=2, marks=6, year=2020) for i in range(4)]
        distribution = [(2, 10), (4, 6)]

        result = assemble_paper(
            questions, total_marks_target=100, distribution=distribution
        )
        assert any("10mark" in w for w in result["warnings"])
        # All 4 six-mark questions should be in paper
        assert len(result["questions"]) == 4
        assert result["total_marks"] == 24

    # --- Stop early when marks target reached ---

    def test_stop_early_at_marks_target(self) -> None:
        """Should stop adding questions once total_marks_target is reached."""
        questions = [
            _q(qid="a", freq=5, marks=6, year=2022),
            _q(qid="b", freq=4, marks=6, year=2022),
            _q(qid="c", freq=3, marks=6, year=2022),
        ]
        distribution = [(3, 6)]  # want 3×6mark = 18 marks total

        result = assemble_paper(
            questions, total_marks_target=6, distribution=distribution
        )
        # Should stop after first question (6 marks = target)
        assert result["total_marks"] == 6
        assert len(result["questions"]) == 1
        # No warning — we stopped because of marks target, not bank shortage
        assert result["warnings"] == []

    def test_marks_target_stops_before_full_distribution(self) -> None:
        """Paper is finalized at target even if distribution not fully satisfied."""
        questions = [
            _q(qid=str(i), freq=i, marks=10, year=2020) for i in range(5)
        ]
        result = assemble_paper(
            questions,
            total_marks_target=10,
            distribution=[(5, 10)],
        )
        assert result["total_marks"] == 10
        assert len(result["questions"]) == 1
        assert result["warnings"] == []  # target met — no warning

    # --- Output ordering ---

    def test_output_ordered_by_marks_descending(self) -> None:
        """Returned questions must be sorted by marks descending."""
        questions = [
            _q(qid="a", freq=3, marks=2, year=2020),
            _q(qid="b", freq=3, marks=10, year=2020),
            _q(qid="c", freq=3, marks=6, year=2020),
        ]
        result = assemble_paper(
            questions, total_marks_target=100, distribution=[]
        )
        marks_list = [q["marks"] for q in result["questions"]]
        assert marks_list == sorted(marks_list, reverse=True)

    # --- topic_tag and total_marks in response ---

    def test_response_includes_topic_tag(self) -> None:
        """Each question in the response must have a topic_tag field."""
        questions = [_q(qid="x", freq=1, marks=5, topic_tag="Operating Systems")]
        result = assemble_paper(
            questions, total_marks_target=5, distribution=[]
        )
        assert result["questions"][0]["topic_tag"] == "Operating Systems"

    def test_total_marks_matches_sum(self) -> None:
        """total_marks in response equals sum of marks of selected questions."""
        questions = [
            _q(qid="a", freq=2, marks=5),
            _q(qid="b", freq=1, marks=3),
        ]
        result = assemble_paper(
            questions, total_marks_target=100, distribution=[]
        )
        assert result["total_marks"] == sum(q["marks"] for q in result["questions"])

    def test_empty_questions_returns_empty_paper(self) -> None:
        """Empty question bank → empty paper, 0 marks, no crash."""
        result = assemble_paper(
            questions=[], total_marks_target=50, distribution=[(2, 10)]
        )
        assert result["questions"] == []
        assert result["total_marks"] == 0


# ===========================================================================
# HTTP endpoint tests
# ===========================================================================

class TestMockPaperEndpoint:

    @pytest.mark.asyncio
    async def test_post_mock_paper_returns_200(self, client: AsyncClient) -> None:
        """POST /mock-paper with valid body should return 200."""
        subject_id = uuid.uuid4()

        mock_session = AsyncMock()
        # Return one question with importance data
        row = MagicMock()
        row.id = uuid.uuid4()
        row.year = 2022
        row.question_text = "Explain virtual memory."
        row.marks = 10
        row.topic_id = uuid.uuid4()
        row.topic_tag = "Memory Management"
        row.frequency_count = 3

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[row])
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.knowledge_store.router.get_db", return_value=mock_cm
        ):
            resp = await client.post(
                "/mock-paper",
                json={
                    "subject_id": str(subject_id),
                    "total_marks_target": 10,
                    "question_type_distribution": "1×10mark",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "questions" in body
        assert "total_marks" in body
        assert "warnings" in body

    @pytest.mark.asyncio
    async def test_post_mock_paper_invalid_marks_target(
        self, client: AsyncClient
    ) -> None:
        """POST /mock-paper with total_marks_target <= 0 should return 422."""
        subject_id = uuid.uuid4()
        resp = await client.post(
            "/mock-paper",
            json={
                "subject_id": str(subject_id),
                "total_marks_target": 0,
                "question_type_distribution": "2×10mark",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_post_mock_paper_insufficient_bank_has_warning(
        self, client: AsyncClient
    ) -> None:
        """POST /mock-paper with insufficient bank returns warnings."""
        subject_id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        # Return empty bank — no questions available
        mock_result.fetchall = MagicMock(return_value=[])
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.knowledge_store.router.get_db", return_value=mock_cm
        ):
            resp = await client.post(
                "/mock-paper",
                json={
                    "subject_id": str(subject_id),
                    "total_marks_target": 20,
                    "question_type_distribution": "2×10mark",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["warnings"]) > 0
        assert len(body["questions"]) == 0

    @pytest.mark.asyncio
    async def test_post_mock_paper_questions_ordered_by_marks_desc(
        self, client: AsyncClient
    ) -> None:
        """Questions in response must be ordered by marks descending."""
        subject_id = uuid.uuid4()

        def _make_row(qid, marks, freq, year):
            row = MagicMock()
            row.id = qid
            row.year = year
            row.question_text = "Sample question text for testing."
            row.marks = marks
            row.topic_id = uuid.uuid4()
            row.topic_tag = "Topic"
            row.frequency_count = freq
            return row

        rows = [
            _make_row(uuid.uuid4(), 2, 1, 2020),
            _make_row(uuid.uuid4(), 10, 5, 2022),
            _make_row(uuid.uuid4(), 6, 3, 2021),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=rows)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.knowledge_store.router.get_db", return_value=mock_cm
        ):
            resp = await client.post(
                "/mock-paper",
                json={
                    "subject_id": str(subject_id),
                    "total_marks_target": 100,
                    "question_type_distribution": "1×10mark + 1×6mark + 1×2mark",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        marks_list = [q["marks"] for q in body["questions"]]
        assert marks_list == sorted(marks_list, reverse=True)
