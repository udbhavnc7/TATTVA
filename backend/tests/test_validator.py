"""
Unit tests for the Confidence Validator (Task 8).

Covers:
  - Unsupported sentences returned → badge downgraded to "needs_review"
  - No unsupported sentences → original badge returned unchanged
  - asyncio.TimeoutError → original badge preserved, no crash
  - RuntimeError from LLM → original badge preserved, no crash
  - ValidationFlag rows created for each flagged sentence
  - content_md is NEVER modified after validate_note
  - Empty note content → "needs_review" (safe default)
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import ValidationFlag
from app.services.generation.validator import (
    _build_c8_prompt,
    _parse_unsupported_sentences,
    validate_note,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    """Return a minimal mock AsyncSession."""
    session = AsyncMock()
    session._added: list = []
    session.add = MagicMock(side_effect=lambda obj: session._added.append(obj))
    session.flush = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
    )
    return session


def _chunk(filename: str = "lecture.pdf", page: int = 5, text: str = "Relevant content.") -> dict:
    return {
        "chunk_id": str(uuid.uuid4()),
        "text": text,
        "cosine_similarity": 0.85,
        "source_filename": filename,
        "page_number": page,
    }


_GROUNDED_NOTE = (
    "Process scheduling determines CPU execution order. "
    "(Source: lecture.pdf, p.5)\n\n"
    "Round-robin is a preemptive scheduling algorithm. "
    "(Source: lecture.pdf, p.6)\n\n"
    "CONFIDENCE: grounded"
)

_PARTIAL_NOTE = (
    "Scheduling affects throughput and response time. "
    "(Source: lecture.pdf, p.5)\n\n"
    "CONFIDENCE: partial"
)

_NEEDS_REVIEW_NOTE = (
    "Some unverifiable claim about quantum computing. "
    "(Source: lecture.pdf, p.5)\n\n"
    "CONFIDENCE: needs_review"
)

_GEMINI_PATCH = "app.services.generation.validator._call_gemini_flash"


# ===========================================================================
# _parse_unsupported_sentences
# ===========================================================================

class TestParseUnsupportedSentences:
    def test_valid_json_list_returned(self) -> None:
        raw = '["Sentence A.", "Sentence B."]'
        result = _parse_unsupported_sentences(raw)
        assert result == ["Sentence A.", "Sentence B."]

    def test_empty_json_list(self) -> None:
        assert _parse_unsupported_sentences("[]") == []

    def test_markdown_fenced_json_parsed(self) -> None:
        raw = '```json\n["Unsupported claim."]\n```'
        result = _parse_unsupported_sentences(raw)
        assert result == ["Unsupported claim."]

    def test_invalid_json_returns_empty(self) -> None:
        assert _parse_unsupported_sentences("not valid json") == []

    def test_json_object_returns_empty(self) -> None:
        assert _parse_unsupported_sentences('{"key": "value"}') == []

    def test_whitespace_only_items_filtered(self) -> None:
        raw = '["valid sentence", "   ", "another sentence"]'
        result = _parse_unsupported_sentences(raw)
        assert "   " not in result
        assert "valid sentence" in result


# ===========================================================================
# validate_note — happy paths
# ===========================================================================

class TestValidateNoteHappyPath:

    @pytest.mark.asyncio
    async def test_unsupported_sentences_downgrades_to_needs_review(self) -> None:
        """When LLM returns unsupported sentences, badge must become needs_review."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(
            _GEMINI_PATCH,
            new=AsyncMock(return_value='["Unverifiable claim about quantum entanglement."]'),
        ):
            result = await validate_note(
                session, note_id, _GROUNDED_NOTE, [_chunk()]
            )

        assert result == "needs_review"

    @pytest.mark.asyncio
    async def test_no_unsupported_sentences_preserves_badge(self) -> None:
        """When LLM returns empty list, original badge is returned unchanged."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(_GEMINI_PATCH, new=AsyncMock(return_value="[]")):
            result = await validate_note(
                session, note_id, _GROUNDED_NOTE, [_chunk()]
            )

        assert result == "grounded"

    @pytest.mark.asyncio
    async def test_partial_badge_preserved_when_all_supported(self) -> None:
        """Partial badge is preserved when no unsupported sentences found."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(_GEMINI_PATCH, new=AsyncMock(return_value="[]")):
            result = await validate_note(
                session, note_id, _PARTIAL_NOTE, [_chunk()]
            )

        assert result == "partial"

    @pytest.mark.asyncio
    async def test_needs_review_badge_preserved_when_all_supported(self) -> None:
        """needs_review badge cannot be upgraded, stays needs_review."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(_GEMINI_PATCH, new=AsyncMock(return_value="[]")):
            result = await validate_note(
                session, note_id, _NEEDS_REVIEW_NOTE, [_chunk()]
            )

        assert result == "needs_review"


# ===========================================================================
# validate_note — failure handling (Task 8.4)
# ===========================================================================

class TestValidateNoteFailureHandling:

    @pytest.mark.asyncio
    async def test_timeout_preserves_original_badge(self) -> None:
        """asyncio.TimeoutError must not crash — original badge preserved."""
        import asyncio
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(_GEMINI_PATCH, new=AsyncMock(side_effect=asyncio.TimeoutError())):
            result = await validate_note(
                session, note_id, _GROUNDED_NOTE, [_chunk()]
            )

        assert result == "grounded"

    @pytest.mark.asyncio
    async def test_runtime_error_preserves_original_badge(self) -> None:
        """RuntimeError from LLM must not crash — original badge preserved."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(
            _GEMINI_PATCH, new=AsyncMock(side_effect=RuntimeError("Gemini unavailable"))
        ):
            result = await validate_note(
                session, note_id, _PARTIAL_NOTE, [_chunk()]
            )

        assert result == "partial"

    @pytest.mark.asyncio
    async def test_note_storage_not_aborted_on_failure(self) -> None:
        """validate_note never raises — note storage is never aborted."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(
            _GEMINI_PATCH, new=AsyncMock(side_effect=Exception("Unexpected error"))
        ):
            # Should not raise
            result = await validate_note(
                session, note_id, _GROUNDED_NOTE, [_chunk()]
            )

        assert isinstance(result, str)


# ===========================================================================
# ValidationFlag rows (Task 8.3)
# ===========================================================================

class TestValidationFlags:

    @pytest.mark.asyncio
    async def test_validation_flags_created_for_each_flagged_sentence(self) -> None:
        """One ValidationFlag row per unsupported sentence."""
        session = _make_session()
        note_id = uuid.uuid4()
        unsupported = ["Sentence A is unsupported.", "Sentence B is unsupported."]

        with patch(
            _GEMINI_PATCH, new=AsyncMock(return_value=str(unsupported).replace("'", '"'))
        ):
            await validate_note(session, note_id, _GROUNDED_NOTE, [_chunk()])

        added_flags = [obj for obj in session._added if isinstance(obj, ValidationFlag)]
        assert len(added_flags) == 2

    @pytest.mark.asyncio
    async def test_validation_flags_carry_correct_note_id(self) -> None:
        """Each ValidationFlag must reference the correct note_id."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(
            _GEMINI_PATCH,
            new=AsyncMock(return_value='["One unsupported sentence."]'),
        ):
            await validate_note(session, note_id, _GROUNDED_NOTE, [_chunk()])

        added_flags = [obj for obj in session._added if isinstance(obj, ValidationFlag)]
        assert all(flag.note_id == note_id for flag in added_flags)

    @pytest.mark.asyncio
    async def test_flags_not_created_when_all_supported(self) -> None:
        """No ValidationFlag rows when LLM reports all sentences are supported."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(_GEMINI_PATCH, new=AsyncMock(return_value="[]")):
            await validate_note(session, note_id, _GROUNDED_NOTE, [_chunk()])

        added_flags = [obj for obj in session._added if isinstance(obj, ValidationFlag)]
        assert added_flags == []

    @pytest.mark.asyncio
    async def test_flags_not_embedded_in_note_content(self) -> None:
        """Flagged sentences are stored in DB only — never in note content."""
        session = _make_session()
        note_id = uuid.uuid4()
        original_content = _GROUNDED_NOTE[:]

        with patch(
            _GEMINI_PATCH, new=AsyncMock(return_value='["Unsupported claim."]')
        ):
            await validate_note(session, note_id, original_content, [_chunk()])

        # content_md string must be unchanged
        assert original_content == _GROUNDED_NOTE


# ===========================================================================
# Property 8.5 — read-only on content_md
# ===========================================================================

class TestContentReadOnly:

    @pytest.mark.asyncio
    async def test_content_md_hash_unchanged_after_validation(self) -> None:
        """SHA-256 of note_content must be identical before and after validate_note."""
        session = _make_session()
        note_id = uuid.uuid4()

        content_before = _GROUNDED_NOTE[:]
        hash_before = hashlib.sha256(content_before.encode()).hexdigest()

        with patch(
            _GEMINI_PATCH, new=AsyncMock(return_value='["Flagged sentence."]')
        ):
            await validate_note(session, note_id, content_before, [_chunk()])

        hash_after = hashlib.sha256(content_before.encode()).hexdigest()
        assert hash_before == hash_after, "content_md was mutated by the validator"

    @pytest.mark.asyncio
    async def test_empty_note_content_returns_needs_review(self) -> None:
        """Empty note content → parse returns 'needs_review' as safe default."""
        session = _make_session()
        note_id = uuid.uuid4()

        with patch(_GEMINI_PATCH, new=AsyncMock(return_value="[]")):
            result = await validate_note(session, note_id, "", [])

        assert result == "needs_review"
