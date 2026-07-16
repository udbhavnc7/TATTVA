"""
Unit tests for the PYQ Analyzer (Task 10.7).

Covers:
  - Valid POST /pyqs: 201 with stored PYQ record
  - Invalid year (below 2000, above current year): 400 field="year"
  - Invalid marks (0, 101): 400 field="marks"
  - Invalid question_text (9 chars, 2001 chars): 400 field="question_text"
  - Unmatched topic: is_unmatched=True, topic_id=None stored
  - POST /pyqs/recalculate: verify SQL is executed, not LLM
  - GET /pyqs with subject_id filter

All tests mock google.generativeai and the database session.
"""

from __future__ import annotations

import datetime
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.knowledge_store.pyq_service import (
    YEAR_MIN,
    MARKS_MIN,
    MARKS_MAX,
    QUESTION_TEXT_MIN,
    QUESTION_TEXT_MAX,
    get_current_year,
    validate_pyq_fields,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pyq_mock(
    pyq_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    topic_id: uuid.UUID | None = None,
    is_unmatched: bool = False,
    year: int = 2022,
    marks: int = 5,
    question_text: str = "What is the definition of operating system?",
    difficulty: str = "medium",
    difficulty_note: str = "Standard recall question.",
    secondary_topics: list | None = None,
) -> MagicMock:
    obj = MagicMock()
    obj.id = pyq_id or uuid.uuid4()
    obj.subject_id = subject_id or uuid.uuid4()
    obj.topic_id = topic_id
    obj.is_unmatched = is_unmatched
    obj.year = year
    obj.marks = marks
    obj.question_text = question_text
    obj.difficulty = difficulty
    obj.difficulty_note = difficulty_note
    obj.secondary_topics = secondary_topics or []
    obj.created_at = datetime.datetime.now(datetime.timezone.utc)
    return obj


def _make_db_mock(pyq_mock: MagicMock | None = None) -> tuple[AsyncMock, AsyncMock]:
    """Return (mock_session, mock_cm) pair."""
    mock_session = AsyncMock()
    # Default: empty topic list (no topics available) → forces is_unmatched
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            fetchall=MagicMock(return_value=[]),
            scalars=MagicMock(
                return_value=MagicMock(
                    first=MagicMock(return_value=None),
                    all=MagicMock(return_value=[]),
                )
            ),
        )
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    if pyq_mock is not None:
        mock_session.refresh = AsyncMock(
            side_effect=lambda obj: (
                setattr(obj, "id", pyq_mock.id)
                or setattr(obj, "topic_id", pyq_mock.topic_id)
                or setattr(obj, "is_unmatched", pyq_mock.is_unmatched)
                or setattr(obj, "difficulty", pyq_mock.difficulty)
                or setattr(obj, "difficulty_note", pyq_mock.difficulty_note)
                or setattr(obj, "secondary_topics", pyq_mock.secondary_topics)
                or setattr(obj, "created_at", pyq_mock.created_at)
                or setattr(obj, "year", pyq_mock.year)
                or setattr(obj, "marks", pyq_mock.marks)
                or setattr(obj, "question_text", pyq_mock.question_text)
                or setattr(obj, "subject_id", pyq_mock.subject_id)
            )
        )
    else:
        mock_session.refresh = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_cm


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ===========================================================================
# Service-layer unit tests (validate_pyq_fields)
# ===========================================================================


class TestValidatePyqFields:
    """Direct tests for the validation helper function."""

    def test_valid_fields_returns_none(self) -> None:
        current_year = get_current_year()
        assert validate_pyq_fields(current_year, 5, "A" * 20) is None

    def test_year_below_2000_returns_year_error(self) -> None:
        err = validate_pyq_fields(1999, 5, "A" * 20)
        assert err is not None
        assert err["field"] == "year"

    def test_year_above_current_returns_year_error(self) -> None:
        future_year = get_current_year() + 1
        err = validate_pyq_fields(future_year, 5, "A" * 20)
        assert err is not None
        assert err["field"] == "year"

    def test_year_2000_is_valid(self) -> None:
        assert validate_pyq_fields(2000, 5, "A" * 20) is None

    def test_year_current_is_valid(self) -> None:
        assert validate_pyq_fields(get_current_year(), 5, "A" * 20) is None

    def test_marks_zero_returns_marks_error(self) -> None:
        err = validate_pyq_fields(2022, 0, "A" * 20)
        assert err is not None
        assert err["field"] == "marks"

    def test_marks_101_returns_marks_error(self) -> None:
        err = validate_pyq_fields(2022, 101, "A" * 20)
        assert err is not None
        assert err["field"] == "marks"

    def test_marks_1_is_valid(self) -> None:
        assert validate_pyq_fields(2022, 1, "A" * 20) is None

    def test_marks_100_is_valid(self) -> None:
        assert validate_pyq_fields(2022, 100, "A" * 20) is None

    def test_question_text_9_chars_returns_question_text_error(self) -> None:
        err = validate_pyq_fields(2022, 5, "A" * 9)
        assert err is not None
        assert err["field"] == "question_text"

    def test_question_text_2001_chars_returns_question_text_error(self) -> None:
        err = validate_pyq_fields(2022, 5, "A" * 2001)
        assert err is not None
        assert err["field"] == "question_text"

    def test_question_text_10_chars_is_valid(self) -> None:
        assert validate_pyq_fields(2022, 5, "A" * 10) is None

    def test_question_text_2000_chars_is_valid(self) -> None:
        assert validate_pyq_fields(2022, 5, "A" * 2000) is None

    def test_year_invalid_takes_priority_over_marks(self) -> None:
        """Year is checked first."""
        err = validate_pyq_fields(1999, 0, "A" * 9)
        assert err is not None
        assert err["field"] == "year"

    def test_marks_invalid_takes_priority_over_question_text(self) -> None:
        """Marks is checked second."""
        err = validate_pyq_fields(2022, 0, "A" * 9)
        assert err is not None
        assert err["field"] == "marks"


# ===========================================================================
# HTTP endpoint tests
# ===========================================================================


class TestPostPyqs:
    """Tests for POST /pyqs endpoint."""

    @pytest.mark.asyncio
    async def test_valid_pyq_returns_201(self, client: AsyncClient) -> None:
        """Valid body must return 201 with a stored PYQ record."""
        subject_id = uuid.uuid4()
        pyq_mock = _make_pyq_mock(subject_id=subject_id)
        _, mock_cm = _make_db_mock(pyq_mock)

        with (
            patch("app.services.knowledge_store.router.get_db", return_value=mock_cm),
            patch("google.generativeai.GenerativeModel") as mock_model_cls,
        ):
            mock_model = MagicMock()
            mock_model_cls.return_value = mock_model
            mock_response = MagicMock()
            mock_response.text = (
                '{"matched_topic_id": null, "confidence": "low", '
                '"difficulty": "medium", "difficulty_note": "Standard recall."}'
            )
            mock_model.generate_content.return_value = mock_response

            resp = await client.post(
                "/pyqs",
                json={
                    "subject_id": str(subject_id),
                    "year": 2022,
                    "question_text": "What is the definition of operating system?",
                    "marks": 5,
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["subject_id"] == str(subject_id)

    @pytest.mark.asyncio
    async def test_invalid_year_below_2000_returns_400_field_year(
        self, client: AsyncClient
    ) -> None:
        """year=1999 must return 400 with field='year'."""
        subject_id = uuid.uuid4()
        resp = await client.post(
            "/pyqs",
            json={
                "subject_id": str(subject_id),
                "year": 1999,
                "question_text": "What is an operating system?",
                "marks": 5,
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "invalid_field"
        assert detail["field"] == "year"

    @pytest.mark.asyncio
    async def test_invalid_year_above_current_returns_400_field_year(
        self, client: AsyncClient
    ) -> None:
        """year=current+1 must return 400 with field='year'."""
        subject_id = uuid.uuid4()
        future_year = get_current_year() + 1
        resp = await client.post(
            "/pyqs",
            json={
                "subject_id": str(subject_id),
                "year": future_year,
                "question_text": "What is an operating system?",
                "marks": 5,
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "invalid_field"
        assert detail["field"] == "year"

    @pytest.mark.asyncio
    async def test_invalid_marks_zero_returns_400_field_marks(
        self, client: AsyncClient
    ) -> None:
        """marks=0 must return 400 with field='marks'."""
        subject_id = uuid.uuid4()
        resp = await client.post(
            "/pyqs",
            json={
                "subject_id": str(subject_id),
                "year": 2022,
                "question_text": "What is an operating system?",
                "marks": 0,
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "invalid_field"
        assert detail["field"] == "marks"

    @pytest.mark.asyncio
    async def test_invalid_marks_101_returns_400_field_marks(
        self, client: AsyncClient
    ) -> None:
        """marks=101 must return 400 with field='marks'."""
        subject_id = uuid.uuid4()
        resp = await client.post(
            "/pyqs",
            json={
                "subject_id": str(subject_id),
                "year": 2022,
                "question_text": "What is an operating system?",
                "marks": 101,
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "invalid_field"
        assert detail["field"] == "marks"

    @pytest.mark.asyncio
    async def test_invalid_question_text_too_short_returns_400(
        self, client: AsyncClient
    ) -> None:
        """9-char question_text must return 400 with field='question_text'."""
        subject_id = uuid.uuid4()
        resp = await client.post(
            "/pyqs",
            json={
                "subject_id": str(subject_id),
                "year": 2022,
                "question_text": "A" * 9,
                "marks": 5,
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "invalid_field"
        assert detail["field"] == "question_text"

    @pytest.mark.asyncio
    async def test_invalid_question_text_too_long_returns_400(
        self, client: AsyncClient
    ) -> None:
        """2001-char question_text must return 400 with field='question_text'."""
        subject_id = uuid.uuid4()
        resp = await client.post(
            "/pyqs",
            json={
                "subject_id": str(subject_id),
                "year": 2022,
                "question_text": "A" * 2001,
                "marks": 5,
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "invalid_field"
        assert detail["field"] == "question_text"

    @pytest.mark.asyncio
    async def test_unmatched_topic_stored_with_is_unmatched_true(
        self, client: AsyncClient
    ) -> None:
        """
        When LLM returns no confident match, PYQ must be stored with
        is_unmatched=True and topic_id=None.
        """
        subject_id = uuid.uuid4()
        pyq_mock = _make_pyq_mock(
            subject_id=subject_id,
            topic_id=None,
            is_unmatched=True,
        )
        _, mock_cm = _make_db_mock(pyq_mock)

        with (
            patch("app.services.knowledge_store.router.get_db", return_value=mock_cm),
            patch("google.generativeai.GenerativeModel") as mock_model_cls,
        ):
            mock_model = MagicMock()
            mock_model_cls.return_value = mock_model
            mock_response = MagicMock()
            mock_response.text = (
                '{"matched_topic_id": null, "confidence": "low", '
                '"difficulty": "easy", "difficulty_note": "No match found."}'
            )
            mock_model.generate_content.return_value = mock_response

            resp = await client.post(
                "/pyqs",
                json={
                    "subject_id": str(subject_id),
                    "year": 2022,
                    "question_text": "Explain the concept of virtual memory.",
                    "marks": 10,
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["is_unmatched"] is True
        assert body["topic_id"] is None


class TestPostPyqsRecalculate:
    """Tests for POST /pyqs/recalculate endpoint."""

    @pytest.mark.asyncio
    async def test_recalculate_executes_sql_not_llm(self, client: AsyncClient) -> None:
        """
        POST /pyqs/recalculate must execute the deterministic SQL query.
        It must NOT call any LLM function.
        """
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.rowcount = 3
        mock_session.execute = AsyncMock(return_value=execute_result)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.knowledge_store.router.get_db", return_value=mock_cm),
            patch("google.generativeai.GenerativeModel") as mock_model_cls,
        ):
            resp = await client.post("/pyqs/recalculate")
            # LLM must NOT have been called
            mock_model_cls.assert_not_called()

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        # execute must have been called (the SQL upsert)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_recalculate_returns_ok_status(self, client: AsyncClient) -> None:
        """Response must contain status='ok'."""
        mock_session = AsyncMock()
        execute_result = MagicMock()
        execute_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=execute_result)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.post("/pyqs/recalculate")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestGetPyqs:
    """Tests for GET /pyqs endpoint."""

    @pytest.mark.asyncio
    async def test_get_pyqs_no_filter_returns_list(self, client: AsyncClient) -> None:
        """GET /pyqs without filters returns all PYQs as a list."""
        pyq1 = _make_pyq_mock(year=2021)
        pyq2 = _make_pyq_mock(year=2022)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[pyq1, pyq2]))
                )
            )
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get("/pyqs")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 2

    @pytest.mark.asyncio
    async def test_get_pyqs_with_subject_id_filter(self, client: AsyncClient) -> None:
        """GET /pyqs?subject_id=<UUID> filters by subject."""
        subject_id = uuid.uuid4()
        pyq1 = _make_pyq_mock(subject_id=subject_id)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[pyq1]))
                )
            )
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/pyqs?subject_id={subject_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["subject_id"] == str(subject_id)

    @pytest.mark.asyncio
    async def test_get_pyqs_is_unmatched_filter(self, client: AsyncClient) -> None:
        """GET /pyqs?is_unmatched=true returns only unmatched PYQs."""
        unmatched_pyq = _make_pyq_mock(is_unmatched=True, topic_id=None)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[unmatched_pyq]))
                )
            )
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get("/pyqs?is_unmatched=true")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["is_unmatched"] is True


class TestGetTopicImportance:
    """Tests for GET /topics/{id}/importance endpoint."""

    @pytest.mark.asyncio
    async def test_topic_with_no_pyqs_returns_frequency_zero(
        self, client: AsyncClient
    ) -> None:
        """Topic with no PYQ records must return frequency_count=0."""
        topic_id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
            )
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/topics/{topic_id}/importance")

        assert resp.status_code == 200
        body = resp.json()
        assert body["topic_id"] == str(topic_id)
        assert body["frequency_count"] == 0

    @pytest.mark.asyncio
    async def test_topic_with_pyqs_returns_correct_count(
        self, client: AsyncClient
    ) -> None:
        """Topic with matched PYQs returns frequency_count > 0."""
        topic_id = uuid.uuid4()
        importance_mock = MagicMock()
        importance_mock.topic_id = topic_id
        importance_mock.frequency_count = 7
        importance_mock.difficulty_avg = 2.0
        importance_mock.last_recalculated = datetime.datetime.now(datetime.timezone.utc)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=importance_mock))
                )
            )
        )
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/topics/{topic_id}/importance")

        assert resp.status_code == 200
        body = resp.json()
        assert body["frequency_count"] == 7
        assert body["topic_id"] == str(topic_id)


class TestSqlCountVerification:
    """Verify that recalculate uses SQL COUNT, not LLM."""

    @pytest.mark.asyncio
    async def test_recalculate_calls_execute_once_with_sql(self) -> None:
        """
        The recalculate_topic_importance function must call session.execute
        exactly once with the SQL upsert statement.
        """
        from app.services.knowledge_store.pyq_service import recalculate_topic_importance

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 5
        mock_session.execute = AsyncMock(return_value=result_mock)

        rowcount = await recalculate_topic_importance(mock_session)

        # Must have executed exactly once
        mock_session.execute.assert_called_once()
        # The call argument must be a text() SQL clause (not a string to LLM)
        call_args = mock_session.execute.call_args
        sql_arg = call_args[0][0]
        # The SQL text should be a SQLAlchemy TextClause
        from sqlalchemy import text as sa_text
        assert hasattr(sql_arg, "text") or str(sql_arg).strip().upper().startswith("INSERT"), (
            f"Expected SQL INSERT statement, got: {sql_arg}"
        )
        assert rowcount == 5
