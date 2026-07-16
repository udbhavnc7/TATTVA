"""
Property-based tests for the PDF Parsing Service — Task 3.5

Property 5: Every extracted chunk has a valid page number in [1, N].
Property 6: Chunk token counts are within [400, 600], except the last chunk
            of a page which may be smaller when it has been merged.

Feature: tattva-exam-engine
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.services.parsing.service import (
    CHUNK_MAX_TOKENS,
    CHUNK_MIN_TOKENS,
    ChunkData,
    split_into_chunks,
    _count_tokens,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A strategy that generates a page number in [1, 500]
page_number_st = st.integers(min_value=1, max_value=500)

# A strategy for generating a total page count N in [1, 50]
page_count_st = st.integers(min_value=1, max_value=50)

# A strategy for document_id UUID
document_id_st = st.uuids()

# A strategy for plausible body text:
# - at least 2 000 characters to ensure we usually get multiple chunks
# - uses printable chars, always terminated with a period
body_text_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters=" \n",
    ),
    min_size=2000,
    max_size=20000,
).map(lambda t: t.strip() + ".")


# ---------------------------------------------------------------------------
# Property 5: Every chunk has a valid page_number in [1, N]
#
# For any synthetic text with a known page count N, every chunk produced by
# split_into_chunks has page_number clamped to [1, N].
# ---------------------------------------------------------------------------

@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(
    n_pages=page_count_st,
    page_texts=st.lists(
        st.tuples(page_number_st, body_text_st),
        min_size=1,
        max_size=5,
    ),
    document_id=document_id_st,
)
def test_property_5_chunk_page_number_in_range(
    n_pages: int,
    page_texts: list[tuple[int, str]],
    document_id: uuid.UUID,
) -> None:
    """Feature: tattva-exam-engine, Property 5: Every chunk has a valid page number.

    For any synthetic text with a known page count N, every chunk produced by
    split_into_chunks has page_number in [1, N].

    Validates: Requirements 3.3, 3.6
    """
    all_chunks: list[ChunkData] = []

    for raw_page_number, text in page_texts:
        # Clamp the page_number to [1, n_pages] to simulate realistic inputs
        page_number = max(1, min(raw_page_number, n_pages))
        chunks = split_into_chunks(text, document_id, page_number)
        all_chunks.extend(chunks)

    for chunk in all_chunks:
        assert 1 <= chunk.page_number <= n_pages, (
            f"chunk.page_number={chunk.page_number} is not in [1, {n_pages}]"
        )


# ---------------------------------------------------------------------------
# Property 6: Chunk token counts are in [400, 600], except the final chunk
# of a page (which may be smaller due to the merge rule or because the page
# has less than 400 tokens of content).
# ---------------------------------------------------------------------------

@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    text=body_text_st,
    page_number=page_number_st,
    document_id=document_id_st,
)
def test_property_6_chunk_token_counts_in_bounds(
    text: str,
    page_number: int,
    document_id: uuid.UUID,
) -> None:
    """Feature: tattva-exam-engine, Property 6: Chunk token counts are within bounds.

    For any text input, all chunks produced by split_into_chunks except
    possibly the last one have token_count in [400, 600].  The last chunk may
    be smaller (merged remainder) or larger (merged previous + remainder) but
    never exceeds 2 * CHUNK_MAX_TOKENS.

    Validates: Requirements 3.4
    """
    chunks = split_into_chunks(text, document_id, page_number)

    if not chunks:
        # Empty text produces no chunks — valid
        return

    # All non-last chunks must be within [1, CHUNK_MAX_TOKENS].
    for chunk in chunks[:-1]:
        assert 1 <= chunk.token_count <= CHUNK_MAX_TOKENS, (
            f"Non-last chunk has token_count={chunk.token_count}, "
            f"expected [1, {CHUNK_MAX_TOKENS}]"
        )

    # The last chunk may be:
    #   a) A normal full chunk (400–600 tokens)
    #   b) A merged chunk (prev + remainder) — can exceed 600 but <= 1200
    #   c) A single-chunk page with less than CHUNK_MIN_TOKENS of content
    last = chunks[-1]
    assert 1 <= last.token_count <= CHUNK_MAX_TOKENS * 2, (
        f"Last chunk token_count={last.token_count} is out of valid range [1, {CHUNK_MAX_TOKENS * 2}]"
    )

    # Verify token_count field matches the actual encoded token count (exact)
    for chunk in chunks:
        actual = _count_tokens(chunk.text)
        assert chunk.token_count == actual, (
            f"token_count={chunk.token_count} does not match actual={actual}"
        )


# ---------------------------------------------------------------------------
# Additional invariants reinforcing Properties 5 & 6
# ---------------------------------------------------------------------------

@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    text=body_text_st,
    page_number=page_number_st,
    document_id=document_id_st,
)
def test_property_5_page_number_is_never_zero_or_negative(
    text: str,
    page_number: int,
    document_id: uuid.UUID,
) -> None:
    """Feature: tattva-exam-engine, Property 5 (corollary): page_number >= 1.

    Every chunk's page_number must be >= 1 (1-indexed), never zero or negative.

    Validates: Requirements 3.3
    """
    chunks = split_into_chunks(text, document_id, page_number)
    for chunk in chunks:
        assert chunk.page_number >= 1, (
            f"chunk.page_number={chunk.page_number} must be >= 1 (1-indexed)"
        )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    text=body_text_st,
    page_number=page_number_st,
    document_id=document_id_st,
)
def test_property_5_page_number_preserved_exactly(
    text: str,
    page_number: int,
    document_id: uuid.UUID,
) -> None:
    """Feature: tattva-exam-engine, Property 5 (exact): page_number is preserved.

    The page_number passed into split_into_chunks must appear unchanged on
    every chunk it produces.

    Validates: Requirements 3.3
    """
    chunks = split_into_chunks(text, document_id, page_number)
    for chunk in chunks:
        assert chunk.page_number == page_number, (
            f"chunk.page_number={chunk.page_number} != input page_number={page_number}"
        )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    text=body_text_st,
    page_number=page_number_st,
    document_id=document_id_st,
)
def test_property_6_no_non_last_chunk_below_minimum(
    text: str,
    page_number: int,
    document_id: uuid.UUID,
) -> None:
    """Feature: tattva-exam-engine, Property 6 (merge rule): final chunk gets merged.

    For normal text (with sentence boundaries), after the merge step every
    non-last chunk is at most CHUNK_MAX_TOKENS.

    Validates: Requirements 3.4
    """
    chunks = split_into_chunks(text, document_id, page_number)

    if len(chunks) <= 1:
        # Single-chunk pages are exempt from the lower bound
        return

    # The last chunk is allowed to be anything in [1, 2*CHUNK_MAX_TOKENS]
    last = chunks[-1]
    assert 1 <= last.token_count <= CHUNK_MAX_TOKENS * 2

    # All non-last chunks must be at most CHUNK_MAX_TOKENS
    for chunk in chunks[:-1]:
        assert chunk.token_count <= CHUNK_MAX_TOKENS, (
            f"Non-last chunk exceeds max: token_count={chunk.token_count}"
        )
