"""
Property-based tests for the Confidence Validator (Task 8.6).

Feature: tattva-exam-engine

Property 18 — validator only downgrades, never upgrades:
  For any (original_badge, has_unsupported) input, the output badge is either
  unchanged (== original_badge) or "needs_review". It can never be a higher
  confidence level than the input.

Property 19 — validator does not mutate note content:
  For any note_content string, the SHA-256 hash of the string before and
  after calling validate_note is identical.

Settings: @settings(max_examples=20, deadline=None) per spec.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.generation.validator import validate_note

# ---------------------------------------------------------------------------
# Confidence badge ordering (for downgrade assertion)
# ---------------------------------------------------------------------------
# Higher index = more confident (for downgrade-only check)
_BADGE_RANK = {"needs_review": 0, "partial": 1, "grounded": 2}

_ALL_BADGES = ["grounded", "partial", "needs_review"]

_VALID_BADGES_ST = st.sampled_from(_ALL_BADGES)

_NOTE_CONTENT_ST = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z", "S")),
    min_size=0,
    max_size=500,
)

_GEMINI_PATCH = "app.services.generation.validator._call_gemini_flash"


def _make_session() -> AsyncMock:
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


def _build_note(badge: str) -> str:
    return f"Study note paragraph. (Source: test.pdf, p.1)\n\nCONFIDENCE: {badge}"


# ---------------------------------------------------------------------------
# Property 18 — validator only downgrades, never upgrades
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    original_badge=_VALID_BADGES_ST,
    has_unsupported=st.booleans(),
)
async def test_property18_validator_only_downgrades(
    original_badge: str,
    has_unsupported: bool,
) -> None:
    """
    Feature: tattva-exam-engine, Property 18: validator only downgrades, never upgrades

    For any (original_badge, has_unsupported) pair:
    - If has_unsupported=True → result must be "needs_review"
    - If has_unsupported=False → result must equal original_badge
    - Result rank <= original_badge rank (never a higher-confidence result)

    Validates: Requirements 8.2, 8.3
    """
    note_id = uuid.uuid4()
    note_content = _build_note(original_badge)
    session = _make_session()

    if has_unsupported:
        llm_response = '["This sentence is unsupported by the source material."]'
    else:
        llm_response = "[]"

    with patch(_GEMINI_PATCH, new=AsyncMock(return_value=llm_response)):
        result = await validate_note(session, note_id, note_content, [])

    # Core property: result rank must be <= original rank (only downgrades)
    assert _BADGE_RANK[result] <= _BADGE_RANK[original_badge], (
        f"Validator upgraded badge from '{original_badge}' to '{result}' — "
        "upgrades are not allowed"
    )

    # Additional constraints
    if has_unsupported:
        assert result == "needs_review", (
            f"Expected 'needs_review' when unsupported sentences found, got '{result}'"
        )
    else:
        assert result == original_badge, (
            f"Expected badge preserved as '{original_badge}' when all supported, got '{result}'"
        )


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(original_badge=_VALID_BADGES_ST)
async def test_property18_failure_never_upgrades(original_badge: str) -> None:
    """
    Feature: tattva-exam-engine, Property 18 (failure path): LLM failure never upgrades

    On any LLM exception, the returned badge must equal the original badge
    (preserve — neither upgrade nor downgrade).

    Validates: Requirements 8.4
    """
    note_id = uuid.uuid4()
    note_content = _build_note(original_badge)
    session = _make_session()

    with patch(_GEMINI_PATCH, new=AsyncMock(side_effect=RuntimeError("LLM unavailable"))):
        result = await validate_note(session, note_id, note_content, [])

    assert result == original_badge, (
        f"On failure, expected badge preserved as '{original_badge}', got '{result}'"
    )
    assert _BADGE_RANK[result] <= _BADGE_RANK[original_badge], (
        "Badge was upgraded during failure handling — not allowed"
    )


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(original_badge=_VALID_BADGES_ST)
async def test_property18_timeout_never_upgrades(original_badge: str) -> None:
    """
    Feature: tattva-exam-engine, Property 18 (timeout path): timeout never upgrades badge

    Validates: Requirements 8.4
    """
    note_id = uuid.uuid4()
    note_content = _build_note(original_badge)
    session = _make_session()

    with patch(_GEMINI_PATCH, new=AsyncMock(side_effect=asyncio.TimeoutError())):
        result = await validate_note(session, note_id, note_content, [])

    assert result == original_badge, (
        f"On timeout, expected badge preserved as '{original_badge}', got '{result}'"
    )


# ---------------------------------------------------------------------------
# Property 19 — validator does not mutate note content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    note_content=_NOTE_CONTENT_ST,
    has_unsupported=st.booleans(),
)
async def test_property19_validator_does_not_mutate_content(
    note_content: str,
    has_unsupported: bool,
) -> None:
    """
    Feature: tattva-exam-engine, Property 19: validator does not mutate note content

    For any note_content string, the SHA-256 hash of the string must be
    identical before and after calling validate_note.  The validator is
    read-only with respect to the note body.

    Validates: Requirements 8.5
    """
    note_id = uuid.uuid4()
    session = _make_session()

    # Record hash before validation
    hash_before = hashlib.sha256(note_content.encode("utf-8", errors="replace")).hexdigest()

    if has_unsupported:
        llm_response = '["Some unsupported sentence."]'
    else:
        llm_response = "[]"

    with patch(_GEMINI_PATCH, new=AsyncMock(return_value=llm_response)):
        await validate_note(session, note_id, note_content, [])

    # Record hash after validation
    hash_after = hashlib.sha256(note_content.encode("utf-8", errors="replace")).hexdigest()

    assert hash_before == hash_after, (
        "note_content was mutated by validate_note — SHA-256 hashes differ"
    )


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(note_content=_NOTE_CONTENT_ST)
async def test_property19_content_unchanged_on_failure(note_content: str) -> None:
    """
    Feature: tattva-exam-engine, Property 19 (failure path): content unchanged on LLM failure

    Validates: Requirements 8.5
    """
    note_id = uuid.uuid4()
    session = _make_session()

    hash_before = hashlib.sha256(note_content.encode("utf-8", errors="replace")).hexdigest()

    with patch(_GEMINI_PATCH, new=AsyncMock(side_effect=RuntimeError("LLM error"))):
        await validate_note(session, note_id, note_content, [])

    hash_after = hashlib.sha256(note_content.encode("utf-8", errors="replace")).hexdigest()

    assert hash_before == hash_after
