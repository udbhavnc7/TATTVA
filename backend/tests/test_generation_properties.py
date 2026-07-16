"""
Property-based tests for the Grounded Note Generation Service (Task 7.7).

Feature: tattva-exam-engine

Three properties under test (20 examples each, deadline=None):

  Property 15 — low similarity triggers refusal, no note written:
    For any set of chunk similarities all strictly below 0.5,
    generate_note raises CoverageInsufficient and never calls session.add().

  Property 16 — every paragraph has a citation:
    For any note content string whose non-empty, non-blank paragraphs are
    present, each paragraph contains the pattern '(Source: *.pdf, p.<N>)'.

  Property 17 — confidence badge is always a valid value:
    For any arbitrary string fed to _parse_confidence_line, the result is
    always one of {"grounded", "partial", "needs_review"}.

All tests use @settings(max_examples=20, deadline=None,
suppress_health_check=[HealthCheck.too_slow]).
"""

from __future__ import annotations

import re
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.generation.service import (
    CoverageInsufficient,
    CONFIDENCE_VALUES,
    _parse_confidence_line,
    generate_note,
)

# ---------------------------------------------------------------------------
# Shared strategy helpers
# ---------------------------------------------------------------------------

# Similarities strictly below the 0.5 gate
_low_sim_strategy = st.floats(min_value=0.0, max_value=0.4999, allow_nan=False)

# Similarities at or above the gate
_high_sim_strategy = st.floats(min_value=0.5, max_value=1.0, allow_nan=False)

# A non-empty list of low-similarity chunks (1–5 items)
_low_chunk_list_strategy = st.lists(
    _low_sim_strategy,
    min_size=1,
    max_size=5,
)

# Arbitrary text that may or may not contain a CONFIDENCE line
_arbitrary_text_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=0,
    max_size=500,
)

# Patch targets
_PATCH_GEMINI = "app.services.generation.service._call_gemini"
_PATCH_SEARCH = "app.services.generation.service.semantic_search"
_PATCH_TOPIC = "app.services.generation.service.get_topic_by_id"
_PATCH_VALIDATE = "app.services.generation.service.validate_note"
_PATCH_COMPUTE_HASH = "app.services.generation.diff.compute_topic_hash"
_PATCH_HASH_CHANGED = "app.services.generation.diff.check_hash_changed"
_PATCH_APPLY_BUMP = "app.services.generation.diff.apply_version_bump"


# ---------------------------------------------------------------------------
# Property 15 — low similarity triggers refusal, no note written
#
# Validates: Requirements 7.2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(similarities=_low_chunk_list_strategy)
async def test_property15_low_similarity_raises_coverage_insufficient(
    similarities: list[float],
) -> None:
    """
    Feature: tattva-exam-engine, Property 15: low similarity triggers refusal

    For any non-empty set of chunk similarities all strictly below 0.5,
    generate_note MUST:
      1. Raise CoverageInsufficient.
      2. Never call session.add() (no Note is written to the DB).

    Validates: Requirements 7.2
    """
    topic_id = uuid.uuid4()

    # Build topic mock
    mock_topic = MagicMock()
    mock_topic.id = topic_id
    mock_topic.name = "Test Topic"
    mock_topic.content_hash = None
    mock_topic.version = 1

    # Build chunks from the generated similarities — all below 0.5
    chunks = [
        {
            "chunk_id": str(uuid.uuid4()),
            "text": "Some text about the topic.",
            "cosine_similarity": sim,
            "source_filename": "doc.pdf",
            "page_number": 1,
            "topic_id": str(topic_id),
            "module_id": str(uuid.uuid4()),
            "subject_id": str(uuid.uuid4()),
        }
        for sim in similarities
    ]

    # Verify all similarities are actually below threshold (generator guarantee)
    assert all(c["cosine_similarity"] < 0.5 for c in chunks), (
        "Strategy produced a similarity >= 0.5; this should never happen."
    )

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=None))
            )
        )
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    with (
        patch(_PATCH_TOPIC, new=AsyncMock(return_value=mock_topic)),
        patch(_PATCH_SEARCH, new=AsyncMock(return_value=chunks)),
        patch(_PATCH_GEMINI, new=AsyncMock(return_value="Should not be called")),
    ):
        with pytest.raises(CoverageInsufficient):
            await generate_note(
                session=mock_session,
                topic_id=topic_id,
                depth="2mark",
            )

    # Property assertion: no note was written
    mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Property 16 — every paragraph has a citation
#
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------


def _paragraphs_without_citation(content: str) -> list[str]:
    """
    Return paragraphs in *content* that do NOT contain a valid citation.

    A paragraph is a non-empty sequence of lines separated by a blank line.
    A valid citation matches the pattern: (Source: <name>.pdf, p.<integer>)
    """
    citation_re = re.compile(r"\(Source:\s+[^,]+\.pdf,\s*p\.\d+\)")

    # Split on blank lines to get paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]

    return [p for p in paragraphs if not citation_re.search(p)]


# Strategy: build content where every paragraph includes a citation
_filename_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_",
    min_size=3,
    max_size=20,
)

_page_num_strategy = st.integers(min_value=1, max_value=999)

_sentence_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd", "Zs"),
        whitelist_characters=" ,.:;-",
    ),
    min_size=5,
    max_size=80,
)


@st.composite
def _cited_paragraph(draw) -> str:
    """Draw a paragraph that always ends with a valid citation."""
    body = draw(_sentence_strategy)
    filename = draw(_filename_strategy)
    page = draw(_page_num_strategy)
    # Normalise body — remove embedded citation-like patterns to keep test clean
    body = re.sub(r"\(Source:.*?\)", "", body).strip()
    if not body:
        body = "Topic explanation here"
    return f"{body} (Source: {filename}.pdf, p.{page})"


@st.composite
def _cited_note_content(draw) -> str:
    """Draw a multi-paragraph note where every paragraph has a citation."""
    num_paragraphs = draw(st.integers(min_value=1, max_value=5))
    paragraphs = [draw(_cited_paragraph()) for _ in range(num_paragraphs)]
    # Add the CONFIDENCE line at the end (separate paragraph)
    badge = draw(st.sampled_from(["grounded", "partial", "needs_review"]))
    paragraphs.append(f"CONFIDENCE: {badge}")
    return "\n\n".join(paragraphs)


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(content=_cited_note_content())
def test_property16_every_paragraph_has_citation(content: str) -> None:
    """
    Feature: tattva-exam-engine, Property 16: every paragraph has a citation

    For any note content string whose paragraphs each include a valid
    (Source: <filename>.pdf, p.<N>) citation, no paragraph should fail
    the citation check.

    This validates that our citation-detection regex correctly identifies
    properly-cited paragraphs and that the LLM output format is verifiable.

    Validates: Requirements 7.3
    """
    # Remove the trailing CONFIDENCE line before checking paragraphs
    lines = content.rstrip().split("\n")
    if lines and lines[-1].startswith("CONFIDENCE:"):
        content_without_badge = "\n".join(lines[:-1]).rstrip()
    else:
        content_without_badge = content

    if not content_without_badge.strip():
        # No paragraphs beyond the CONFIDENCE line — trivially satisfied
        return

    missing_citations = _paragraphs_without_citation(content_without_badge)

    assert missing_citations == [], (
        f"The following paragraphs are missing citations:\n"
        + "\n---\n".join(missing_citations)
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    body=_sentence_strategy,
    filename=_filename_strategy,
    page=_page_num_strategy,
)
def test_property16_citation_pattern_detected(
    body: str, filename: str, page: int
) -> None:
    """
    Feature: tattva-exam-engine, Property 16: citation pattern detection

    For any paragraph whose last segment is '(Source: X.pdf, p.N)',
    the citation-detection regex must find the citation.

    Validates: Requirements 7.3
    """
    citation_re = re.compile(r"\(Source:\s+[^,]+\.pdf,\s*p\.\d+\)")

    paragraph = f"{body} (Source: {filename}.pdf, p.{page})"
    assert citation_re.search(paragraph) is not None, (
        f"Citation pattern not detected in paragraph: {paragraph!r}"
    )


# ---------------------------------------------------------------------------
# Property 17 — confidence badge is always a valid value
#
# Validates: Requirements 7.4
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(content=_arbitrary_text_strategy)
def test_property17_confidence_badge_always_valid(content: str) -> None:
    """
    Feature: tattva-exam-engine, Property 17: confidence badge is always valid

    For ANY string fed to _parse_confidence_line, the result must always
    be one of {"grounded", "partial", "needs_review"}.

    The function must never raise an exception or return an unexpected value.

    Validates: Requirements 7.4
    """
    try:
        result = _parse_confidence_line(content)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"_parse_confidence_line raised an exception for input {content!r}: {exc}"
        ) from exc

    assert result in CONFIDENCE_VALUES, (
        f"_parse_confidence_line returned {result!r} for input {content!r}. "
        f"Expected one of {CONFIDENCE_VALUES}."
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    body=_arbitrary_text_strategy,
    badge=st.sampled_from(["grounded", "partial", "needs_review"]),
)
def test_property17_valid_confidence_line_round_trips(body: str, badge: str) -> None:
    """
    Feature: tattva-exam-engine, Property 17: valid confidence line round-trips

    If the last non-empty line of a content string is exactly
    'CONFIDENCE: <badge>', _parse_confidence_line must return that badge.

    Validates: Requirements 7.4
    """
    # Construct content ending with a valid CONFIDENCE line
    content = f"{body}\nCONFIDENCE: {badge}"
    result = _parse_confidence_line(content)
    assert result == badge, (
        f"Expected badge={badge!r} but got {result!r} "
        f"for content ending with 'CONFIDENCE: {badge}'"
    )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    content=st.one_of(
        # Content with no CONFIDENCE line at all
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=0,
            max_size=200,
        ).filter(lambda s: "CONFIDENCE:" not in s.upper().rsplit("\n", 1)[-1]),
        # Content whose last line is not a recognized badge
        st.just("some body text\nCONFIDENCE: unknown_value"),
        st.just("body\nCONFIDENCE:"),
        st.just(""),
    )
)
def test_property17_missing_or_malformed_returns_needs_review(
    content: str,
) -> None:
    """
    Feature: tattva-exam-engine, Property 17: fallback to needs_review

    When content has no valid CONFIDENCE line (missing, empty, or with an
    unrecognized badge), _parse_confidence_line must return 'needs_review'.

    Validates: Requirements 7.4
    """
    result = _parse_confidence_line(content)
    # result must always be a valid badge value (covers the broader property)
    assert result in CONFIDENCE_VALUES, (
        f"Unexpected result {result!r} for content {content!r}"
    )
    # For the specific cases constructed above (no valid CONFIDENCE line),
    # the safe default is needs_review
    last_line = content.rstrip("\n\r ").rsplit("\n", 1)[-1].strip().upper()
    has_valid_badge = last_line in {
        "CONFIDENCE: GROUNDED",
        "CONFIDENCE: PARTIAL",
        "CONFIDENCE: NEEDS_REVIEW",
    }
    if not has_valid_badge:
        assert result == "needs_review", (
            f"Expected 'needs_review' fallback but got {result!r} "
            f"for content {content!r}"
        )
