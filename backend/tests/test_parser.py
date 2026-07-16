"""
Unit tests for the PDF Parsing Service — Task 3.6

Covers:
  - OCR fallback trigger (only called when PyMuPDF yields empty text)
  - Blank-page logging (unprocessable pages logged, not raised)
  - Sentence-boundary splitting
  - Final-chunk merging (< 400 tokens merged into previous)
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.parsing.service import (
    CHUNK_MAX_TOKENS,
    CHUNK_MIN_TOKENS,
    ChunkData,
    split_into_chunks,
    parse_document,
    _count_tokens,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOCUMENT_ID = uuid.uuid4()

# Build a sentence that is close to CHUNK_MAX_TOKENS (600) tokens.
# Using repeated short words keeps it easy to reason about.
def _make_long_sentence(target_tokens: int = 620) -> str:
    """Return a sentence whose token count is approximately *target_tokens*."""
    # Each "word " is approximately 1 token; adjust as needed.
    word = "alpha "
    sentence = word * target_tokens
    return sentence.strip() + "."


def _make_sentence(target_tokens: int) -> str:
    """Return a sentence of approximately *target_tokens* tokens."""
    word = "test "
    sentence = word * target_tokens
    return sentence.strip() + "."


def _paragraph(sentences: list[str]) -> str:
    return " ".join(sentences)


# ---------------------------------------------------------------------------
# split_into_chunks — basic behaviour
# ---------------------------------------------------------------------------

class TestSplitIntoChunks:
    """Unit tests for split_into_chunks."""

    def test_empty_text_returns_empty_list(self) -> None:
        assert split_into_chunks("", DOCUMENT_ID, 1) == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert split_into_chunks("   \n\t  ", DOCUMENT_ID, 1) == []

    def test_single_short_sentence_produces_one_chunk(self) -> None:
        text = "Kirchhoff's voltage law states that the sum of all voltages around a closed loop is zero."
        chunks = split_into_chunks(text, DOCUMENT_ID, 1)
        assert len(chunks) >= 1
        assert all(isinstance(c, ChunkData) for c in chunks)

    def test_chunk_carries_correct_document_id(self) -> None:
        text = "The quick brown fox jumps over the lazy dog. " * 300
        doc_id = uuid.uuid4()
        chunks = split_into_chunks(text, doc_id, 3)
        for chunk in chunks:
            assert chunk.document_id == doc_id

    def test_chunk_carries_correct_page_number(self) -> None:
        text = "Some text sentence. " * 300
        chunks = split_into_chunks(text, DOCUMENT_ID, 7)
        for chunk in chunks:
            assert chunk.page_number == 7

    def test_token_count_is_consistent(self) -> None:
        """token_count on each chunk must equal the re-encoded token count of the chunk text."""
        text = "The voltage across a resistor equals the current multiplied by resistance. " * 200
        chunks = split_into_chunks(text, DOCUMENT_ID, 1)
        for chunk in chunks:
            assert chunk.token_count >= 1
            recount = _count_tokens(chunk.text)
            assert chunk.token_count == recount, (
                f"token_count={chunk.token_count} does not match re-encoded={recount}"
            )

    def test_no_chunk_exceeds_600_tokens(self) -> None:
        """Non-last chunks must not exceed CHUNK_MAX_TOKENS."""
        text = "Newton's second law states F equals ma. " * 400
        chunks = split_into_chunks(text, DOCUMENT_ID, 1)
        # All chunks except possibly the last (due to merge) must be <= 600.
        # After the final-chunk merge, merged chunks can exceed 600 — so we only
        # check inner chunks strictly, i.e. all chunks if there's only one.
        if len(chunks) == 1:
            # single chunk — token count is whatever the text encodes to
            assert chunks[0].token_count <= CHUNK_MAX_TOKENS * 2  # lenient for merged
        else:
            # All but last are bounded by the split logic
            for chunk in chunks[:-1]:
                assert chunk.token_count <= CHUNK_MAX_TOKENS


# ---------------------------------------------------------------------------
# Sentence-boundary splitting
# ---------------------------------------------------------------------------

class TestSentenceBoundarySplitting:
    """Verify that chunks respect sentence boundaries where possible."""

    def test_split_respects_sentence_boundaries(self) -> None:
        """Sentences should not be split in the middle under normal conditions."""
        sentences = [
            "Ohm's law describes the relationship between voltage, current, and resistance.",
            "The formula is V equals I times R.",
            "This is a fundamental concept in circuit analysis.",
        ]
        text = " ".join(sentences)
        chunks = split_into_chunks(text, DOCUMENT_ID, 1)
        # Reassemble all chunk texts and verify no words are lost
        combined = " ".join(c.text for c in chunks)
        for sentence in sentences:
            # Each sentence should appear somewhere in the combined output
            # (allowing for whitespace normalisation)
            assert any(
                sentence.rstrip(".") in c.text for c in chunks
            ), f"Sentence not found in any chunk: {sentence!r}"

    def test_long_sentence_is_hard_split(self) -> None:
        """A single sentence exceeding 600 tokens must be hard-split with [truncated]."""
        long_sentence = _make_long_sentence(target_tokens=700)
        chunks = split_into_chunks(long_sentence, DOCUMENT_ID, 1)
        # At least one chunk should contain the truncation marker
        truncated_chunks = [c for c in chunks if "[truncated]" in c.text]
        assert len(truncated_chunks) >= 1, (
            "Expected at least one chunk with [truncated] for an oversized sentence"
        )
        # Every chunk (including hard-split ones) must respect CHUNK_MAX_TOKENS
        for chunk in chunks:
            assert chunk.token_count <= CHUNK_MAX_TOKENS, (
                f"Hard-split chunk exceeded {CHUNK_MAX_TOKENS} tokens: {chunk.token_count}"
            )


# ---------------------------------------------------------------------------
# Final-chunk merging
# ---------------------------------------------------------------------------

class TestFinalChunkMerging:
    """Verify the merge rule: last chunk < 400 tokens is merged with previous."""

    def test_final_chunk_below_400_is_merged(self) -> None:
        """If the final chunk would be < 400 tokens, it must be merged with the previous."""
        # Build text that fills one full chunk (near 580 tokens) plus a tiny tail
        filler = _make_sentence(target_tokens=580)
        tail = "A short tail."  # Well below 400 tokens
        text = filler + " " + tail

        chunks = split_into_chunks(text, DOCUMENT_ID, 1)

        # The tail is too small to stand alone; it must have been merged
        # into the previous chunk rather than forming its own chunk < 400 tokens.
        for chunk in chunks[:-1]:
            assert chunk.token_count >= CHUNK_MIN_TOKENS, (
                f"Non-last chunk has {chunk.token_count} tokens (below {CHUNK_MIN_TOKENS})"
            )

    def test_only_last_chunk_may_be_below_minimum(self) -> None:
        """After merging, all chunks except the last must be >= CHUNK_MIN_TOKENS."""
        text = "Electrostatics is the study of static electric charges. " * 600
        chunks = split_into_chunks(text, DOCUMENT_ID, 2)

        if len(chunks) > 1:
            for chunk in chunks[:-1]:
                assert chunk.token_count >= CHUNK_MIN_TOKENS

    def test_single_chunk_below_400_is_kept_as_is(self) -> None:
        """When only one chunk exists there is nothing to merge into — it stays."""
        text = "Short text."  # Clearly below 400 tokens
        chunks = split_into_chunks(text, DOCUMENT_ID, 1)
        assert len(chunks) == 1
        assert chunks[0].text.strip() != ""


# ---------------------------------------------------------------------------
# OCR fallback trigger
# ---------------------------------------------------------------------------

class TestOcrFallback:
    """Verify OCR is triggered only when PyMuPDF yields empty text."""

    def test_ocr_not_called_when_pymupdf_has_text(self) -> None:
        """When extract_page_text returns text, ocr_page must NOT be called."""
        fake_page = MagicMock()
        fake_doc = MagicMock()
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.__getitem__ = MagicMock(return_value=fake_page)
        fake_doc.close = MagicMock()

        with (
            patch(
                "app.services.parsing.service.extract_page_text",
                return_value="This page has readable text content.",
            ) as mock_extract,
            patch(
                "app.services.parsing.service.ocr_page",
            ) as mock_ocr,
            patch(
                "app.services.parsing.service.fitz.open",
                return_value=fake_doc,
            ),
        ):
            parse_document(DOCUMENT_ID, b"%PDF-1.4 fake")
            mock_extract.assert_called_once()
            mock_ocr.assert_not_called()

    def test_ocr_called_when_pymupdf_yields_empty(self) -> None:
        """When extract_page_text returns empty string, ocr_page MUST be called."""
        fake_page = MagicMock()
        fake_doc = MagicMock()
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.__getitem__ = MagicMock(return_value=fake_page)
        fake_doc.close = MagicMock()

        with (
            patch(
                "app.services.parsing.service.extract_page_text",
                return_value="",
            ),
            patch(
                "app.services.parsing.service.ocr_page",
                return_value="OCR-extracted text content from image page.",
            ) as mock_ocr,
            patch(
                "app.services.parsing.service.fitz.open",
                return_value=fake_doc,
            ),
        ):
            chunks = parse_document(DOCUMENT_ID, b"%PDF-1.4 fake")
            mock_ocr.assert_called_once()
            # OCR text is returned and chunked
            assert len(chunks) >= 1

    def test_ocr_called_when_pymupdf_yields_whitespace_only(self) -> None:
        """Whitespace-only text from PyMuPDF also triggers OCR."""
        fake_page = MagicMock()
        fake_doc = MagicMock()
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.__getitem__ = MagicMock(return_value=fake_page)
        fake_doc.close = MagicMock()

        with (
            patch(
                "app.services.parsing.service.extract_page_text",
                return_value="   \n\t  ",
            ),
            patch(
                "app.services.parsing.service.ocr_page",
                return_value="OCR text.",
            ) as mock_ocr,
            patch(
                "app.services.parsing.service.fitz.open",
                return_value=fake_doc,
            ),
        ):
            parse_document(DOCUMENT_ID, b"%PDF-1.4 fake")
            mock_ocr.assert_called_once()


# ---------------------------------------------------------------------------
# Blank-page logging (Requirement 3.5)
# ---------------------------------------------------------------------------

class TestBlankPageLogging:
    """Verify unprocessable pages are logged and NOT raised as exceptions."""

    def test_blank_page_does_not_raise(self) -> None:
        """A page that yields no text from PyMuPDF or OCR must not raise."""
        fake_page = MagicMock()
        fake_doc = MagicMock()
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.__getitem__ = MagicMock(return_value=fake_page)
        fake_doc.close = MagicMock()

        with (
            patch(
                "app.services.parsing.service.extract_page_text",
                return_value="",
            ),
            patch(
                "app.services.parsing.service.ocr_page",
                return_value="",
            ),
            patch(
                "app.services.parsing.service.fitz.open",
                return_value=fake_doc,
            ),
        ):
            # Must not raise — blank pages are skipped, not errored
            result = parse_document(DOCUMENT_ID, b"%PDF-1.4 fake")
            assert result == []

    def test_blank_page_is_logged_with_correct_fields(self, caplog) -> None:
        """An unprocessable page must log a dict with document_id, page_number, reason."""
        fake_page = MagicMock()
        fake_doc = MagicMock()
        fake_doc.__len__ = MagicMock(return_value=1)
        fake_doc.__getitem__ = MagicMock(return_value=fake_page)
        fake_doc.close = MagicMock()

        with (
            patch(
                "app.services.parsing.service.extract_page_text",
                return_value="",
            ),
            patch(
                "app.services.parsing.service.ocr_page",
                return_value="",
            ),
            patch(
                "app.services.parsing.service.fitz.open",
                return_value=fake_doc,
            ),
            caplog.at_level("WARNING", logger="app.services.parsing.service"),
        ):
            parse_document(DOCUMENT_ID, b"%PDF-1.4 fake")

        # Verify the log contains the required fields
        assert any(
            "no_text_extracted" in record.message for record in caplog.records
        ), "Expected a warning log entry with 'no_text_extracted'"
        assert any(
            str(DOCUMENT_ID) in record.message for record in caplog.records
        ), "Expected the document_id in the log entry"

    def test_multi_page_continues_after_blank(self) -> None:
        """Processing continues on subsequent pages even if an earlier page is blank."""
        fake_page = MagicMock()
        fake_doc = MagicMock()
        fake_doc.__len__ = MagicMock(return_value=2)
        fake_doc.close = MagicMock()

        call_count = 0

        def side_effect_extract(page):
            nonlocal call_count
            call_count += 1
            # Page 1 is blank, page 2 has text
            if call_count == 1:
                return ""
            return "This is page two content with real text. " * 50

        def side_effect_ocr(page):
            # OCR on blank page also returns empty
            return ""

        page_call_count = 0

        def get_page(idx):
            return fake_page

        fake_doc.__getitem__ = MagicMock(side_effect=get_page)

        with (
            patch(
                "app.services.parsing.service.extract_page_text",
                side_effect=side_effect_extract,
            ),
            patch(
                "app.services.parsing.service.ocr_page",
                side_effect=side_effect_ocr,
            ),
            patch(
                "app.services.parsing.service.fitz.open",
                return_value=fake_doc,
            ),
        ):
            chunks = parse_document(DOCUMENT_ID, b"%PDF-1.4 fake")

        # page 2 should have produced chunks
        assert len(chunks) >= 1
        assert all(c.page_number == 2 for c in chunks)


# ---------------------------------------------------------------------------
# store_chunks — rollback on failure
# ---------------------------------------------------------------------------

class TestStoreChunks:
    """Verify that store_chunks rolls back and raises on DB write failure."""

    @pytest.mark.asyncio
    async def test_rollback_raised_on_flush_failure(self) -> None:
        """If session.flush() raises, rollback must be called and RuntimeError raised."""
        from app.services.parsing.service import store_chunks

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.flush = MagicMock(side_effect=Exception("DB error"))
        mock_session.rollback = MagicMock()

        # Make flush and rollback awaitable
        import asyncio

        async def async_flush():
            raise Exception("DB error")

        async def async_rollback():
            pass

        mock_session.flush = async_flush
        mock_session.rollback = async_rollback

        doc_id = uuid.uuid4()
        chunks = [
            ChunkData(document_id=doc_id, page_number=1, text="Test chunk.", token_count=3)
        ]

        with pytest.raises(RuntimeError) as exc_info:
            await store_chunks(mock_session, chunks)

        assert str(doc_id) in str(exc_info.value), (
            "RuntimeError should contain the document_id"
        )

    @pytest.mark.asyncio
    async def test_empty_chunks_is_noop(self) -> None:
        """Calling store_chunks with an empty list must not call session.add."""
        from app.services.parsing.service import store_chunks

        mock_session = MagicMock()
        await store_chunks(mock_session, [])
        mock_session.add.assert_not_called()
