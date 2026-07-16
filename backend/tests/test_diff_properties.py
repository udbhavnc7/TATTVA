"""
Property-based tests for the Incremental Diff Pipeline (Task 6).

Feature: tattva-exam-engine

Three properties under test:
  Property 9  — Unchanged topic hash causes no downstream processing
  Property 10 — Changed topic hash triggers version increment + hash store + note_versions record
  Property 11 — Version history is monotonically growing (N changes → ≥ N records,
                strictly increasing version numbers)

Each @settings decorator sets max_examples=20 per task requirement.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.db.models import NoteVersion
from app.services.generation.diff import (
    apply_version_bump,
    check_hash_changed,
    compute_topic_hash,
)


# ---------------------------------------------------------------------------
# Async helper — works in Python 3.10+ where get_event_loop() raises
# RuntimeError if no current loop exists (e.g. inside synchronous Hypothesis
# test functions which are not run in an async context).
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an awaitable in a fresh event loop, compatible with Python 3.14."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

# Arbitrary text that can represent topic content (printable Unicode, non-empty)
topic_text_strategy = st.text(min_size=1, max_size=500)

# Pair of *distinct* topic texts so hashes are reliably different
distinct_text_pair = st.tuples(topic_text_strategy, topic_text_strategy).filter(
    lambda pair: compute_topic_hash(pair[0]) != compute_topic_hash(pair[1])
)

# A list of N distinct topic texts (for Property 11)
# We draw N in [2, 6] and then N distinct texts.
def _distinct_text_list(draw):
    """Hypothesis composite strategy: list of 2–6 strings with distinct hashes."""
    n = draw(st.integers(min_value=2, max_value=6))
    texts = draw(
        st.lists(topic_text_strategy, min_size=n * 2, max_size=n * 4).map(
            lambda lst: list({compute_topic_hash(t): t for t in lst}.values())
        ).filter(lambda lst: len(lst) >= n)
    )
    return texts[:n]


@st.composite
def distinct_text_list_strategy(draw):
    return _distinct_text_list(draw)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_topic(content_hash: str | None = None, version: int = 1) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.content_hash = content_hash
    t.version = version
    t.last_updated = datetime.now(timezone.utc)
    return t


def _make_note(topic_id: uuid.UUID | None = None, version: int = 1) -> MagicMock:
    n = MagicMock()
    n.id = uuid.uuid4()
    n.topic_id = topic_id or uuid.uuid4()
    n.version = version
    n.content_md = "## Generated note content"
    n.confidence = "grounded"
    n.generated_at = datetime.now(timezone.utc)
    return n


def _mock_session() -> AsyncMock:
    """Return a mock AsyncSession that records added objects."""
    session = AsyncMock()
    session._added: List[object] = []
    session.add = MagicMock(side_effect=lambda obj: session._added.append(obj))
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Property 9 — Unchanged hash → no downstream processing
# ---------------------------------------------------------------------------

@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=topic_text_strategy)
def test_property9_unchanged_hash_skips_downstream(text: str) -> None:
    """
    Feature: tattva-exam-engine, Property 9: unchanged topic hash causes no downstream processing

    For any topic text, if the stored content_hash equals the hash of the
    same text, check_hash_changed must return False (skip all downstream steps).

    Validates: Requirements 5.2
    """
    new_hash = compute_topic_hash(text)
    # Simulate a topic whose stored hash already matches
    topic = _make_topic(content_hash=new_hash)

    result = check_hash_changed(topic, new_hash)

    assert result is False, (
        f"Expected False (skip downstream) when stored_hash == new_hash "
        f"but got {result!r} for text={text!r}"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=topic_text_strategy)
def test_property9_first_ingestion_no_stored_hash_runs_pipeline(text: str) -> None:
    """
    Feature: tattva-exam-engine, Property 9 (corollary): first ingestion always runs pipeline

    When topic.content_hash is None (never ingested), check_hash_changed must
    return True regardless of the new hash value.

    Validates: Requirements 5.2
    """
    new_hash = compute_topic_hash(text)
    topic = _make_topic(content_hash=None)

    result = check_hash_changed(topic, new_hash)

    assert result is True, (
        f"Expected True (run pipeline) for first ingestion but got {result!r}"
    )


# ---------------------------------------------------------------------------
# Property 10 — Changed hash → version increment + hash stored + NoteVersion written
# ---------------------------------------------------------------------------

@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text_pair=distinct_text_pair)
def test_property10_changed_hash_detected(text_pair: tuple[str, str]) -> None:
    """
    Feature: tattva-exam-engine, Property 10: changed topic hash triggers version increment

    For any pair of topic texts with different hashes, check_hash_changed must
    return True when the new hash differs from the stored hash.

    Validates: Requirements 5.4
    """
    old_text, new_text = text_pair
    stored_hash = compute_topic_hash(old_text)
    new_hash = compute_topic_hash(new_text)

    assert stored_hash != new_hash, "Strategy guaranteed distinct hashes"

    topic = _make_topic(content_hash=stored_hash)
    result = check_hash_changed(topic, new_hash)

    assert result is True, (
        f"Expected True (run pipeline) for hash change but got {result!r}"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text_pair=distinct_text_pair, initial_version=st.integers(min_value=1, max_value=50))
def test_property10_version_incremented_by_exactly_one(
    text_pair: tuple[str, str], initial_version: int
) -> None:
    """
    Feature: tattva-exam-engine, Property 10: changed hash triggers version increment

    For any topic with an initial version V and a changed hash, apply_version_bump
    must set topic.version to V+1 — never more, never less.

    Validates: Requirements 5.4, 5.6
    """
    old_text, new_text = text_pair
    stored_hash = compute_topic_hash(old_text)
    new_hash = compute_topic_hash(new_text)

    topic = _make_topic(content_hash=stored_hash, version=initial_version)
    note = _make_note(topic_id=topic.id, version=initial_version)
    session = _mock_session()

    _run(
        apply_version_bump(session, topic, new_hash, note)
    )

    assert topic.version == initial_version + 1, (
        f"Expected version {initial_version + 1}, got {topic.version}"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text_pair=distinct_text_pair)
def test_property10_new_hash_stored_after_bump(text_pair: tuple[str, str]) -> None:
    """
    Feature: tattva-exam-engine, Property 10 (hash storage): new hash persisted

    After apply_version_bump, topic.content_hash must equal new_hash.

    Validates: Requirements 5.4
    """
    old_text, new_text = text_pair
    stored_hash = compute_topic_hash(old_text)
    new_hash = compute_topic_hash(new_text)

    topic = _make_topic(content_hash=stored_hash)
    note = _make_note(topic_id=topic.id)
    session = _mock_session()

    _run(
        apply_version_bump(session, topic, new_hash, note)
    )

    assert topic.content_hash == new_hash, (
        f"Expected content_hash={new_hash!r}, got {topic.content_hash!r}"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text_pair=distinct_text_pair)
def test_property10_note_versions_record_created(text_pair: tuple[str, str]) -> None:
    """
    Feature: tattva-exam-engine, Property 10 (history record): NoteVersion written

    After apply_version_bump, exactly one NoteVersion must have been added to the
    session, and it must carry the correct topic_id, version (V+1), content_md,
    confidence, and generated_at from the note.

    Validates: Requirements 5.6
    """
    old_text, new_text = text_pair
    stored_hash = compute_topic_hash(old_text)
    new_hash = compute_topic_hash(new_text)
    initial_version = 1

    topic = _make_topic(content_hash=stored_hash, version=initial_version)
    note = _make_note(topic_id=topic.id, version=initial_version)
    note.content_md = "## Property 10 test note"
    note.confidence = "partial"
    session = _mock_session()

    _run(
        apply_version_bump(session, topic, new_hash, note)
    )

    assert len(session._added) == 1, f"Expected 1 NoteVersion, got {len(session._added)}"
    nv = session._added[0]
    assert isinstance(nv, NoteVersion)
    assert nv.topic_id == topic.id
    assert nv.version == initial_version + 1
    assert nv.content_md == note.content_md
    assert nv.confidence == note.confidence
    assert nv.generated_at == note.generated_at


# ---------------------------------------------------------------------------
# Property 11 — Version history is monotonically growing
# ---------------------------------------------------------------------------

@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(texts=distinct_text_list_strategy())
def test_property11_version_history_monotonically_growing(texts: list[str]) -> None:
    """
    Feature: tattva-exam-engine, Property 11: version history is monotonically growing

    After N sequential hash changes (N >= 2), the note_versions records collected
    must:
      1. Number exactly N (one per change).
      2. Have strictly increasing version numbers.

    This test simulates N sequential apply_version_bump calls and verifies the
    accumulated NoteVersion records satisfy both conditions.

    Validates: Requirements 5.5
    """
    n = len(texts)
    assert n >= 2, "Strategy guarantees at least 2 distinct texts"

    topic = _make_topic(content_hash=None, version=1)
    topic_id = topic.id
    note = _make_note(topic_id=topic_id, version=1)

    all_added_versions: list[NoteVersion] = []

    for text in texts:
        new_hash = compute_topic_hash(text)

        session = _mock_session()

        _run(
            apply_version_bump(session, topic, new_hash, note)
        )

        # Collect any NoteVersion objects added this round
        for obj in session._added:
            if isinstance(obj, NoteVersion):
                all_added_versions.append(obj)

        # Update note to reflect new version for next iteration
        note.version = topic.version

    # Condition 1: N records written (one per change)
    assert len(all_added_versions) == n, (
        f"Expected {n} NoteVersion records, got {len(all_added_versions)}"
    )

    # Condition 2: strictly increasing version numbers
    version_numbers = [nv.version for nv in all_added_versions]
    for i in range(1, len(version_numbers)):
        assert version_numbers[i] > version_numbers[i - 1], (
            f"Version numbers not strictly increasing: {version_numbers}"
        )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n_changes=st.integers(min_value=2, max_value=5),
    base_text=topic_text_strategy,
)
def test_property11_version_numbers_start_at_two_and_increment(
    n_changes: int, base_text: str
) -> None:
    """
    Feature: tattva-exam-engine, Property 11 (version numbering): starts at 2, each bump +1

    Given a topic at version=1, after N sequential calls to apply_version_bump,
    the collected NoteVersion records must have version numbers [2, 3, ..., N+1].

    Validates: Requirements 5.5
    """
    topic = _make_topic(content_hash=None, version=1)
    note = _make_note(topic_id=topic.id, version=1)

    collected_versions: list[int] = []

    for i in range(n_changes):
        # Generate a unique hash for each step by appending the iteration index
        unique_text = f"{base_text}__change_{i}"
        new_hash = compute_topic_hash(unique_text)

        session = _mock_session()
        _run(
            apply_version_bump(session, topic, new_hash, note)
        )

        for obj in session._added:
            if isinstance(obj, NoteVersion):
                collected_versions.append(obj.version)

        note.version = topic.version

    expected_versions = list(range(2, n_changes + 2))
    assert collected_versions == expected_versions, (
        f"Expected versions {expected_versions}, got {collected_versions}"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(texts=distinct_text_list_strategy())
def test_property11_no_note_version_rows_ever_deleted(texts: list[str]) -> None:
    """
    Feature: tattva-exam-engine, Property 11 (immutability): note_versions never deleted

    apply_version_bump must ONLY add NoteVersion rows — it must never call
    session.delete() on any NoteVersion instance.

    Validates: Requirements 5.5 (never delete note_versions rows)
    """
    topic = _make_topic(content_hash=None, version=1)
    note = _make_note(topic_id=topic.id)

    for text in texts:
        new_hash = compute_topic_hash(text)
        session = _mock_session()
        # Spy on delete calls
        session.delete = MagicMock()

        _run(
            apply_version_bump(session, topic, new_hash, note)
        )

        # session.delete must never be called
        session.delete.assert_not_called()
        note.version = topic.version
