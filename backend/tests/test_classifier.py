"""
Unit tests for the Classification Service.

Feature: tattva-exam-engine

Covers:
  - validate_classification_output: high / medium / low confidence valid payloads
  - validate_classification_output: rejection cases (missing fields, bad types, long note)
  - classify_document: high confidence path (no retry needed)
  - classify_document: medium confidence path
  - classify_document: low confidence path (pending_review=True, note required)
  - classify_document: retry-then-fail path (both LLM calls fail → returns None,
    document marked classification_failed)
  - create_taxonomy_if_needed: creation order (subject → module → topic)
  - write_classification_record: low-confidence sets pending_review=True, note stored

All tests mock google.generativeai — no real API calls are made.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.services.classification.service import (
    ClassificationResult,
    _call_llm,
    _extract_json_from_response,
    classify_document,
    create_taxonomy_if_needed,
    validate_classification_output,
    write_classification_record,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_high_output() -> dict:
    return {
        "subject": "Operating Systems",
        "module_number": 3,
        "topic": "Process Scheduling",
        "is_new_topic": False,
        "confidence": "high",
    }


def _make_valid_medium_output() -> dict:
    return {
        "subject": "Operating Systems",
        "module_number": 4,
        "topic": "Memory Paging",
        "is_new_topic": True,
        "confidence": "medium",
    }


def _make_valid_low_output() -> dict:
    return {
        "subject": "Networks",
        "module_number": 1,
        "topic": "TCP/IP Overview",
        "is_new_topic": True,
        "confidence": "low",
        "note": "Content partially matches networking topic; unclear module boundary.",
    }


def _make_mock_session() -> AsyncMock:
    """Return an AsyncMock that mimics a minimal AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_execute_returning_none(session: AsyncMock) -> None:
    """Configure session.execute to simulate 'not found' DB queries."""
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=None))
            )
        )
    )


# ---------------------------------------------------------------------------
# validate_classification_output — valid cases
# ---------------------------------------------------------------------------

class TestValidateClassificationOutput:
    """Unit tests for the pure validation helper."""

    def test_high_confidence_valid(self):
        """High-confidence output with no note is valid."""
        assert validate_classification_output(_make_valid_high_output()) is True

    def test_medium_confidence_valid(self):
        """Medium-confidence output with no note is valid."""
        assert validate_classification_output(_make_valid_medium_output()) is True

    def test_low_confidence_with_note_valid(self):
        """Low-confidence output with a non-empty note ≤200 chars is valid."""
        assert validate_classification_output(_make_valid_low_output()) is True

    def test_low_confidence_exact_200_char_note_valid(self):
        """Note of exactly 200 characters is valid."""
        out = _make_valid_low_output()
        out["note"] = "x" * 200
        assert validate_classification_output(out) is True

    def test_high_confidence_with_optional_note_still_valid(self):
        """High-confidence output that includes a note is still valid (note is optional)."""
        out = _make_valid_high_output()
        out["note"] = "Some extra context"
        assert validate_classification_output(out) is True

    # --- Rejection cases ---

    def test_missing_subject_rejected(self):
        out = _make_valid_high_output()
        del out["subject"]
        assert validate_classification_output(out) is False

    def test_empty_subject_rejected(self):
        out = _make_valid_high_output()
        out["subject"] = "   "
        assert validate_classification_output(out) is False

    def test_missing_module_number_rejected(self):
        out = _make_valid_high_output()
        del out["module_number"]
        assert validate_classification_output(out) is False

    def test_string_module_number_rejected(self):
        out = _make_valid_high_output()
        out["module_number"] = "3"  # string, not int
        assert validate_classification_output(out) is False

    def test_missing_topic_rejected(self):
        out = _make_valid_high_output()
        del out["topic"]
        assert validate_classification_output(out) is False

    def test_empty_topic_rejected(self):
        out = _make_valid_high_output()
        out["topic"] = ""
        assert validate_classification_output(out) is False

    def test_missing_is_new_topic_rejected(self):
        out = _make_valid_high_output()
        del out["is_new_topic"]
        assert validate_classification_output(out) is False

    def test_invalid_confidence_value_rejected(self):
        out = _make_valid_high_output()
        out["confidence"] = "very_high"
        assert validate_classification_output(out) is False

    def test_missing_confidence_rejected(self):
        out = _make_valid_high_output()
        del out["confidence"]
        assert validate_classification_output(out) is False

    def test_low_confidence_missing_note_rejected(self):
        """Low confidence without a note must fail validation."""
        out = _make_valid_low_output()
        del out["note"]
        assert validate_classification_output(out) is False

    def test_low_confidence_empty_note_rejected(self):
        out = _make_valid_low_output()
        out["note"] = "   "
        assert validate_classification_output(out) is False

    def test_note_over_200_chars_rejected(self):
        out = _make_valid_low_output()
        out["note"] = "x" * 201
        assert validate_classification_output(out) is False

    def test_not_dict_rejected(self):
        assert validate_classification_output("not a dict") is False  # type: ignore
        assert validate_classification_output(None) is False  # type: ignore
        assert validate_classification_output([1, 2]) is False  # type: ignore


# ---------------------------------------------------------------------------
# _extract_json_from_response
# ---------------------------------------------------------------------------

class TestExtractJsonFromResponse:
    def test_plain_json_parsed(self):
        payload = _make_valid_high_output()
        text = json.dumps(payload)
        result = _extract_json_from_response(text)
        assert result == payload

    def test_json_with_markdown_fences_parsed(self):
        payload = _make_valid_high_output()
        text = f"```json\n{json.dumps(payload)}\n```"
        result = _extract_json_from_response(text)
        assert result == payload

    def test_json_with_plain_fences_parsed(self):
        payload = _make_valid_high_output()
        text = f"```\n{json.dumps(payload)}\n```"
        result = _extract_json_from_response(text)
        assert result == payload

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError):
            _extract_json_from_response("not json at all {{}}")


# ---------------------------------------------------------------------------
# classify_document — happy paths
# ---------------------------------------------------------------------------

class TestClassifyDocument:
    """Integration-style unit tests using mocked LLM and DB session."""

    @pytest.mark.asyncio
    async def test_high_confidence_path_returns_result(self):
        """High-confidence LLM response → ClassificationResult with confidence='high'."""
        doc_id = uuid.uuid4()
        session = _make_mock_session()
        llm_response = json.dumps(_make_valid_high_output())

        with patch(
            "app.services.classification.service._call_llm",
            return_value=llm_response,
        ):
            result = await classify_document(
                document_id=doc_id,
                headings=["Chapter 3: Process Scheduling"],
                content="This chapter covers CPU scheduling algorithms...",
                session=session,
            )

        assert result is not None
        assert result.confidence == "high"
        assert result.subject == "Operating Systems"
        assert result.module_number == 3
        assert result.topic == "Process Scheduling"
        assert result.is_new_topic is False
        assert result.note is None

    @pytest.mark.asyncio
    async def test_medium_confidence_path_returns_result(self):
        """Medium-confidence output → result.confidence == 'medium'."""
        doc_id = uuid.uuid4()
        session = _make_mock_session()
        llm_response = json.dumps(_make_valid_medium_output())

        with patch(
            "app.services.classification.service._call_llm",
            return_value=llm_response,
        ):
            result = await classify_document(
                document_id=doc_id,
                headings=["Memory Management"],
                content="Paging divides memory into fixed-size frames...",
                session=session,
            )

        assert result is not None
        assert result.confidence == "medium"
        assert result.is_new_topic is True

    @pytest.mark.asyncio
    async def test_low_confidence_path_returns_result_with_note(self):
        """Low-confidence output → result.confidence == 'low', note is populated."""
        doc_id = uuid.uuid4()
        session = _make_mock_session()
        llm_response = json.dumps(_make_valid_low_output())

        with patch(
            "app.services.classification.service._call_llm",
            return_value=llm_response,
        ):
            result = await classify_document(
                document_id=doc_id,
                headings=["Introduction to Networks"],
                content="TCP/IP is a suite of communication protocols...",
                session=session,
            )

        assert result is not None
        assert result.confidence == "low"
        assert result.note is not None
        assert len(result.note) <= 200
        assert result.note.strip() != ""

    # ---------------------------------------------------------------------------
    # Retry-then-fail path
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_retry_then_fail_returns_none_and_marks_document_failed(self):
        """
        When both LLM attempts raise RuntimeError, classify_document must:
          - Return None
          - Call _mark_document_failed (which updates document.status)
        """
        doc_id = uuid.uuid4()
        session = _make_mock_session()

        # Simulate existing document found by session.execute
        mock_doc = MagicMock()
        mock_doc.status = "parsing"
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_doc))
                )
            )
        )

        with patch(
            "app.services.classification.service._call_llm",
            side_effect=RuntimeError("LLM unavailable"),
        ) as mock_llm:
            result = await classify_document(
                document_id=doc_id,
                headings=["Heading"],
                content="Some content",
                session=session,
            )

        assert result is None
        # LLM must have been called exactly twice (original + 1 retry)
        assert mock_llm.call_count == 2
        # Document status should have been updated
        assert mock_doc.status == "classification_failed"

    @pytest.mark.asyncio
    async def test_retry_on_json_parse_failure(self):
        """
        First attempt returns malformed JSON; second attempt returns valid JSON.
        Result should be successful from the second attempt.
        """
        doc_id = uuid.uuid4()
        session = _make_mock_session()
        valid_response = json.dumps(_make_valid_high_output())

        call_responses = ["this is not json {{", valid_response]

        with patch(
            "app.services.classification.service._call_llm",
            side_effect=call_responses,
        ):
            result = await classify_document(
                document_id=doc_id,
                headings=["Test"],
                content="Some content",
                session=session,
            )

        assert result is not None
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_retry_on_schema_validation_failure(self):
        """
        First attempt returns JSON that fails schema validation;
        second attempt returns valid JSON → success.
        """
        doc_id = uuid.uuid4()
        session = _make_mock_session()
        invalid_output = {"subject": "OS"}  # missing required fields
        valid_response = json.dumps(_make_valid_medium_output())

        call_responses = [json.dumps(invalid_output), valid_response]

        with patch(
            "app.services.classification.service._call_llm",
            side_effect=call_responses,
        ):
            result = await classify_document(
                document_id=doc_id,
                headings=["Test"],
                content="Some content",
                session=session,
            )

        assert result is not None
        assert result.confidence == "medium"

    @pytest.mark.asyncio
    async def test_both_attempts_fail_returns_none(self):
        """
        Both attempts return invalid JSON → None returned and document marked failed.
        """
        doc_id = uuid.uuid4()
        session = _make_mock_session()
        mock_doc = MagicMock()
        mock_doc.status = "parsing"
        session.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_doc))
                )
            )
        )

        with patch(
            "app.services.classification.service._call_llm",
            side_effect=["not json", "also not json"],
        ):
            result = await classify_document(
                document_id=doc_id,
                headings=["Test"],
                content="Some content",
                session=session,
            )

        assert result is None
        assert mock_doc.status == "classification_failed"


# ---------------------------------------------------------------------------
# create_taxonomy_if_needed — FK ordering
# ---------------------------------------------------------------------------

class TestCreateTaxonomyIfNeeded:
    """Verify that subject → module → topic are created in FK order."""

    @pytest.mark.asyncio
    async def test_creates_subject_then_module_then_topic(self):
        """
        When no records exist, three ORM objects are add()ed in the correct
        FK dependency order: Subject first, Module second, Topic third.
        """
        session = _make_mock_session()
        # All lookups return None → everything needs to be created
        _make_execute_returning_none(session)

        result = ClassificationResult(
            subject="Algorithms",
            module_number=2,
            topic="Sorting Algorithms",
            is_new_topic=True,
            confidence="high",
            note=None,
        )

        # Track add() call order
        add_calls = []
        def track_add(obj):
            add_calls.append(type(obj).__name__)
        session.add.side_effect = track_add

        subject, module, topic = await create_taxonomy_if_needed(session, result)

        # Verify creation order
        assert add_calls == ["Subject", "Module", "Topic"], (
            f"Expected Subject → Module → Topic, got {add_calls}"
        )

    @pytest.mark.asyncio
    async def test_reuses_existing_subject(self):
        """If Subject already exists, it is reused and not re-added."""
        session = _make_mock_session()

        existing_subject = MagicMock(spec=["id", "name", "code"])
        existing_subject.id = uuid.uuid4()
        existing_subject.name = "Data Structures"

        # First execute (subject lookup) → found; subsequent lookups → None
        execute_responses = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_subject)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]
        session.execute = AsyncMock(side_effect=execute_responses)

        add_calls = []
        def track_add(obj):
            add_calls.append(type(obj).__name__)
        session.add.side_effect = track_add

        result = ClassificationResult(
            subject="Data Structures",
            module_number=1,
            topic="Arrays",
            is_new_topic=False,
            confidence="high",
            note=None,
        )

        subject, module, topic = await create_taxonomy_if_needed(session, result)

        # Subject must NOT be in add_calls — it was reused
        assert "Subject" not in add_calls
        assert "Module" in add_calls
        assert "Topic" in add_calls

    @pytest.mark.asyncio
    async def test_reuses_existing_subject_and_module(self):
        """If Subject and Module both exist, only Topic is created."""
        existing_subject = MagicMock(spec=["id", "name"])
        existing_subject.id = uuid.uuid4()
        existing_module = MagicMock(spec=["id", "subject_id", "number", "title"])
        existing_module.id = uuid.uuid4()

        session = _make_mock_session()
        execute_responses = [
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_subject)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_module)))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
        ]
        session.execute = AsyncMock(side_effect=execute_responses)

        add_calls = []
        def track_add(obj):
            add_calls.append(type(obj).__name__)
        session.add.side_effect = track_add

        result = ClassificationResult(
            subject="Data Structures",
            module_number=1,
            topic="Linked Lists",
            is_new_topic=True,
            confidence="medium",
            note=None,
        )

        subject, module, topic = await create_taxonomy_if_needed(session, result)

        assert add_calls == ["Topic"], f"Expected only Topic to be created, got {add_calls}"


# ---------------------------------------------------------------------------
# write_classification_record — confidence paths
# ---------------------------------------------------------------------------

class TestWriteClassificationRecord:
    @pytest.mark.asyncio
    async def test_high_confidence_pending_review_false(self):
        """High confidence → pending_review=False, note=None stored."""
        session = _make_mock_session()
        doc_id = uuid.uuid4()
        result = ClassificationResult(
            subject="OS",
            module_number=1,
            topic="Processes",
            is_new_topic=False,
            confidence="high",
            note=None,
        )

        classification = MagicMock()
        classification.id = uuid.uuid4()

        async def mock_refresh(obj):
            obj.id = classification.id

        session.refresh.side_effect = mock_refresh

        rec = await write_classification_record(
            session=session,
            document_id=doc_id,
            result=result,
            pending_review=False,
        )

        # session.add should have been called with a Classification object
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert added_obj.confidence == "high"
        assert added_obj.pending_review is False
        assert added_obj.note is None

    @pytest.mark.asyncio
    async def test_low_confidence_pending_review_true_note_stored(self):
        """Low confidence → pending_review=True and note stored on the record."""
        session = _make_mock_session()
        doc_id = uuid.uuid4()
        note_text = "Uncertain match; content spans multiple topics."
        result = ClassificationResult(
            subject="Networks",
            module_number=2,
            topic="Routing Protocols",
            is_new_topic=True,
            confidence="low",
            note=note_text,
        )

        async def mock_refresh(obj):
            obj.id = uuid.uuid4()

        session.refresh.side_effect = mock_refresh

        rec = await write_classification_record(
            session=session,
            document_id=doc_id,
            result=result,
            pending_review=True,
        )

        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert added_obj.confidence == "low"
        assert added_obj.pending_review is True
        assert added_obj.note == note_text
        assert len(added_obj.note) <= 200

    @pytest.mark.asyncio
    async def test_medium_confidence_pending_review_false(self):
        """Medium confidence → pending_review=False."""
        session = _make_mock_session()
        doc_id = uuid.uuid4()
        result = ClassificationResult(
            subject="OS",
            module_number=2,
            topic="Virtual Memory",
            is_new_topic=True,
            confidence="medium",
            note=None,
        )

        async def mock_refresh(obj):
            obj.id = uuid.uuid4()

        session.refresh.side_effect = mock_refresh

        await write_classification_record(
            session=session,
            document_id=doc_id,
            result=result,
            pending_review=False,
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.confidence == "medium"
        assert added_obj.pending_review is False


# ---------------------------------------------------------------------------
# Router integration tests
# ---------------------------------------------------------------------------

class TestClassificationRouter:
    """End-to-end router tests using FastAPI test client with mocked service."""

    @pytest.mark.asyncio
    async def test_classify_endpoint_success(self):
        """POST /classify/{id} returns 200 with expected fields on success."""
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        doc_id = uuid.uuid4()
        classification_id = uuid.uuid4()

        high_result = ClassificationResult(
            subject="Operating Systems",
            module_number=3,
            topic="Process Scheduling",
            is_new_topic=False,
            confidence="high",
            note=None,
        )

        # Mock the full pipeline
        with patch(
            "app.services.classification.router.classify_document",
            new=AsyncMock(return_value=high_result),
        ), patch(
            "app.services.classification.router.create_taxonomy_if_needed",
            new=AsyncMock(return_value=(MagicMock(), MagicMock(), MagicMock())),
        ), patch(
            "app.services.classification.router.write_classification_record",
            new=AsyncMock(
                return_value=MagicMock(id=classification_id)
            ),
        ), patch(
            "app.services.classification.router.get_db",
            return_value=_make_async_cm(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/classify/{doc_id}",
                    json={
                        "headings": ["Chapter 3: CPU Scheduling"],
                        "content": "CPU scheduling algorithms allocate processor time...",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["confidence"] == "high"
        assert body["subject"] == "Operating Systems"
        assert body["pending_review"] is False

    @pytest.mark.asyncio
    async def test_classify_endpoint_returns_422_on_failure(self):
        """POST /classify/{id} returns 422 when classification fails."""
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        doc_id = uuid.uuid4()

        with patch(
            "app.services.classification.router.classify_document",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.classification.router.get_db",
            return_value=_make_async_cm(),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    f"/classify/{doc_id}",
                    json={"headings": [], "content": ""},
                )

        assert resp.status_code == 422


def _make_async_cm():
    """Create a context manager mock that yields a minimal session."""
    session = _make_mock_session()
    _make_execute_returning_none(session)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm
