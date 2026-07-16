"""
Unit tests for the Incremental Diff Pipeline (Task 6).

Covers:
  - compute_topic_hash: determinism, whitespace normalization, NFC normalization
  - check_hash_changed: None stored hash → True, same hash → False, different → True
  - apply_version_bump: increments version, sets content_hash, writes NoteVersion;
                        rolls back on flush failure
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.generation.diff import (
    apply_version_bump,
    check_hash_changed,
    compute_topic_hash,
    normalize_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_topic(
    content_hash: str | None = None,
    version: int = 1,
) -> MagicMock:
    """Lightweight Topic-like mock."""
    t = MagicMock()
    t.id = uuid.uuid4()
    t.content_hash = content_hash
    t.version = version
    t.last_updated = datetime.now(timezone.utc)
    return t


def _make_note(
    topic_id: uuid.UUID | None = None,
    version: int = 1,
    content_md: str = "# Sample note",
    confidence: str = "grounded",
) -> MagicMock:
    """Lightweight Note-like mock."""
    n = MagicMock()
    n.id = uuid.uuid4()
    n.topic_id = topic_id or uuid.uuid4()
    n.version = version
    n.content_md = content_md
    n.confidence = confidence
    n.generated_at = datetime.now(timezone.utc)
    return n


# ---------------------------------------------------------------------------
# compute_topic_hash — determinism
# ---------------------------------------------------------------------------

class TestComputeTopicHash:
    """Tests for 6.1 — SHA-256 hash from normalized text."""

    def test_same_text_always_same_hash(self) -> None:
        """Calling compute_topic_hash twice on the same string must yield the same digest."""
        text = "Kirchhoff's Voltage Law and its applications in circuits"
        assert compute_topic_hash(text) == compute_topic_hash(text)

    def test_hash_is_64_hex_chars(self) -> None:
        """SHA-256 hex digest is always 64 lowercase hexadecimal characters."""
        h = compute_topic_hash("any topic text")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_texts_have_different_hashes(self) -> None:
        """Two genuinely different texts should (virtually always) produce different hashes."""
        h1 = compute_topic_hash("Topic A: Forces and Motion")
        h2 = compute_topic_hash("Topic B: Thermodynamics")
        assert h1 != h2

    # --- Whitespace normalization tests ---

    def test_leading_trailing_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace must not affect the hash."""
        assert compute_topic_hash("  hello  ") == compute_topic_hash("hello")

    def test_tabs_and_newlines_stripped(self) -> None:
        """Tabs and newlines at the boundary are treated as whitespace."""
        assert compute_topic_hash("\t\nhello\n\t") == compute_topic_hash("hello")

    def test_internal_whitespace_collapsed(self) -> None:
        """Multiple internal spaces collapse to one space before hashing."""
        assert compute_topic_hash("hello   world") == compute_topic_hash("hello world")

    def test_mixed_whitespace_collapsed(self) -> None:
        """Tabs, newlines, and spaces within text all collapse to single spaces."""
        messy = "hello\t\n  world\r\n  foo"
        clean = "hello world foo"
        assert compute_topic_hash(messy) == compute_topic_hash(clean)

    def test_empty_string(self) -> None:
        """Empty string should hash consistently (not raise)."""
        h = compute_topic_hash("")
        assert len(h) == 64
        # Empty string after normalization is still empty; hash of "" is deterministic
        assert h == hashlib.sha256(b"").hexdigest()

    def test_whitespace_only_string(self) -> None:
        """Whitespace-only string strips to empty, matching empty string hash."""
        assert compute_topic_hash("   \t\n  ") == compute_topic_hash("")

    # --- NFC normalization tests ---

    def test_nfc_normalization_applied(self) -> None:
        """
        Combining character sequences are normalized to NFC before hashing.
        U+00E9 (é precomposed) and U+0065 U+0301 (e + combining acute) should
        produce the same hash after NFC normalization.
        """
        precomposed = "\u00e9"          # é  (NFC)
        decomposed = "e\u0301"          # e + combining acute (NFD)
        # After NFC normalization, both collapse to the same code point
        assert compute_topic_hash(precomposed) == compute_topic_hash(decomposed)

    def test_nfc_normalization_in_context(self) -> None:
        """Full topic text with composed/decomposed variants should hash identically."""
        topic_nfc = unicodedata.normalize("NFC", "Bézier curves in CAD design")
        topic_nfd = unicodedata.normalize("NFD", "Bézier curves in CAD design")
        # After applying our normalization both should yield the same hash
        assert compute_topic_hash(topic_nfc) == compute_topic_hash(topic_nfd)

    def test_hash_matches_manual_computation(self) -> None:
        """
        compute_topic_hash must exactly equal manually constructing the hash from
        the normalized string.
        """
        raw = "  Thermodynamics   — First Law  "
        normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFC", raw).strip())
        expected = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        assert compute_topic_hash(raw) == expected


# ---------------------------------------------------------------------------
# check_hash_changed
# ---------------------------------------------------------------------------

class TestCheckHashChanged:
    """Tests for 6.2 — hash comparison logic."""

    def test_none_stored_hash_returns_true_first_ingestion(self) -> None:
        """
        When topic.content_hash is None (never ingested before),
        check_hash_changed must return True so the full pipeline runs.
        """
        topic = _make_topic(content_hash=None)
        new_hash = compute_topic_hash("some new text")
        assert check_hash_changed(topic, new_hash) is True

    def test_same_hash_returns_false_skip_downstream(self) -> None:
        """
        When new_hash equals the stored hash, downstream must be skipped
        (returns False).
        """
        h = compute_topic_hash("identical content")
        topic = _make_topic(content_hash=h)
        assert check_hash_changed(topic, h) is False

    def test_different_hash_returns_true_run_pipeline(self) -> None:
        """
        When new_hash differs from the stored hash, the pipeline must run
        (returns True).
        """
        stored = compute_topic_hash("original content")
        new = compute_topic_hash("updated content")
        assert stored != new  # sanity check
        topic = _make_topic(content_hash=stored)
        assert check_hash_changed(topic, new) is True

    def test_empty_stored_hash_different_from_new_returns_true(self) -> None:
        """An empty-string stored hash that differs from new_hash triggers pipeline."""
        topic = _make_topic(content_hash="")
        new_hash = compute_topic_hash("some text")
        assert check_hash_changed(topic, new_hash) is True

    def test_whitespace_normalized_same_hash(self) -> None:
        """
        Extra whitespace variant that normalizes to the same text produces the
        same hash → check_hash_changed returns False.
        """
        text_a = "hello world"
        text_b = "hello   world"
        h_stored = compute_topic_hash(text_a)
        h_new = compute_topic_hash(text_b)
        # Both should normalize to the same hash
        assert h_stored == h_new
        topic = _make_topic(content_hash=h_stored)
        assert check_hash_changed(topic, h_new) is False


# ---------------------------------------------------------------------------
# apply_version_bump
# ---------------------------------------------------------------------------

class TestApplyVersionBump:
    """Tests for 6.3 — version bump, hash storage, NoteVersion write."""

    @pytest.mark.asyncio
    async def test_version_incremented_by_one(self) -> None:
        """topic.version must be incremented by exactly 1."""
        topic = _make_topic(content_hash="old" * 16, version=3)
        note = _make_note(topic_id=topic.id, version=3)
        new_hash = "a" * 64

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        await apply_version_bump(mock_session, topic, new_hash, note)

        assert topic.version == 4  # was 3, now 4

    @pytest.mark.asyncio
    async def test_content_hash_updated(self) -> None:
        """topic.content_hash must be set to new_hash."""
        topic = _make_topic(content_hash="old" * 16, version=1)
        note = _make_note(topic_id=topic.id)
        new_hash = "b" * 64

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        await apply_version_bump(mock_session, topic, new_hash, note)

        assert topic.content_hash == new_hash

    @pytest.mark.asyncio
    async def test_note_version_record_written(self) -> None:
        """A NoteVersion instance must be added to the session."""
        topic = _make_topic(content_hash="old" * 16, version=2)
        note = _make_note(topic_id=topic.id, version=2, content_md="## Notes", confidence="partial")
        new_hash = "c" * 64
        doc_id = uuid.uuid4()

        added_objects = []

        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_session.flush = AsyncMock()

        nv = await apply_version_bump(mock_session, topic, new_hash, note, source_document_id=doc_id)

        # One NoteVersion was added
        assert len(added_objects) == 1
        added = added_objects[0]

        from app.db.models import NoteVersion
        assert isinstance(added, NoteVersion)
        assert added.note_id == note.id
        assert added.topic_id == topic.id
        assert added.version == 3          # incremented topic.version
        assert added.content_md == note.content_md
        assert added.confidence == note.confidence
        assert added.source_document_id == doc_id

    @pytest.mark.asyncio
    async def test_flush_called_once(self) -> None:
        """session.flush() must be called exactly once to surface constraint errors."""
        topic = _make_topic(content_hash="old" * 16, version=1)
        note = _make_note()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        await apply_version_bump(mock_session, topic, "d" * 64, note)

        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_rollback_on_flush_failure(self) -> None:
        """
        If session.flush() raises, the exception must propagate.
        The caller (get_db context manager) is responsible for the rollback;
        here we verify the exception is NOT swallowed by apply_version_bump.
        """
        topic = _make_topic(content_hash="old" * 16, version=1)
        note = _make_note()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock(side_effect=RuntimeError("note_versions write failed"))

        with pytest.raises(RuntimeError, match="note_versions write failed"):
            await apply_version_bump(mock_session, topic, "e" * 64, note)

    @pytest.mark.asyncio
    async def test_version_incremented_from_one(self) -> None:
        """Test the common first-change scenario: version goes from 1 to 2."""
        topic = _make_topic(content_hash=None, version=1)
        note = _make_note(topic_id=topic.id, version=1)
        new_hash = compute_topic_hash("first actual content")

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        await apply_version_bump(mock_session, topic, new_hash, note)

        assert topic.version == 2

    @pytest.mark.asyncio
    async def test_source_document_id_optional(self) -> None:
        """apply_version_bump should work without a source_document_id (None)."""
        topic = _make_topic(version=1)
        note = _make_note()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        nv = await apply_version_bump(mock_session, topic, "f" * 64, note, source_document_id=None)
        assert nv.source_document_id is None
