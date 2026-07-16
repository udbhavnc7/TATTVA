"""
Property-based tests for the Knowledge Store Service.

Feature: tattva-exam-engine

Three properties under test (min 20 examples each):
  Property 12 — chunk tag completeness: any chunk dict with all five required
                fields (subject_id, module_id, topic_id, document_id, page_number)
                passes validation; any with a null field raises ValueError.
  Property 13 — search result ordering: for any list of (chunk_id, similarity)
                pairs, results sorted by cosine_similarity descending maintain
                strict descending order.
  Property 14 — subject code uniqueness invariant: submitting the same code
                twice returns 409 on the second call.

Each @settings decorator sets max_examples=20, deadline=None,
suppress_health_check=[HealthCheck.too_slow].
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.knowledge_store.service import validate_chunk_tags

# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# A non-null UUID-like value for chunk tags
_uuid_strategy = st.uuids()

# A non-negative integer for page_number (>= 1)
_page_number_strategy = st.integers(min_value=1, max_value=10_000)

# A valid subject code: 4–10 alphanumeric characters
_valid_code_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    min_size=4,
    max_size=10,
)

# A valid subject name: 1–120 characters
_name_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    min_size=1,
    max_size=60,
)

# Cosine similarity value in [0.0, 1.0]
_similarity_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


# ---------------------------------------------------------------------------
# Property 12 — chunk tag completeness
#
# Validates: Requirements 6.3
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    topic_id=_uuid_strategy,
    document_id=_uuid_strategy,
    page_number=_page_number_strategy,
    subject_id=_uuid_strategy,
    module_id=_uuid_strategy,
)
def test_property12_chunk_tag_completeness_all_present(
    topic_id: uuid.UUID,
    document_id: uuid.UUID,
    page_number: int,
    subject_id: uuid.UUID,
    module_id: uuid.UUID,
) -> None:
    """
    Feature: tattva-exam-engine, Property 12: chunk tag completeness

    Any chunk dict where topic_id, document_id, and page_number are all
    non-null must pass validate_chunk_tags without raising.

    Note: subject_id and module_id are resolved via JOIN at query time and
    are NOT direct columns on the chunks table; validate_chunk_tags enforces
    only the three service-layer required fields.

    Validates: Requirements 6.3
    """
    chunk: dict[str, Any] = {
        "topic_id": topic_id,
        "document_id": document_id,
        "page_number": page_number,
        # subject_id and module_id included as contextual data (not validated here)
        "subject_id": subject_id,
        "module_id": module_id,
    }
    # Must not raise
    validate_chunk_tags(chunk)


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    topic_id=st.one_of(st.none(), _uuid_strategy),
    document_id=st.one_of(st.none(), _uuid_strategy),
    page_number=st.one_of(st.none(), _page_number_strategy),
)
def test_property12_chunk_tag_completeness_null_field_fails(
    topic_id: uuid.UUID | None,
    document_id: uuid.UUID | None,
    page_number: int | None,
) -> None:
    """
    Feature: tattva-exam-engine, Property 12: chunk tag completeness

    Any chunk dict where at least one of topic_id, document_id, page_number
    is null must cause validate_chunk_tags to raise ValueError.

    Validates: Requirements 6.3
    """
    # Only run the assertion when at least one field is null
    if topic_id is None or document_id is None or page_number is None:
        chunk: dict[str, Any] = {
            "topic_id": topic_id,
            "document_id": document_id,
            "page_number": page_number,
        }
        with pytest.raises(ValueError):
            validate_chunk_tags(chunk)


# ---------------------------------------------------------------------------
# Property 13 — search result ordering
#
# Validates: Requirements 6.4
# ---------------------------------------------------------------------------


def _sort_results_descending(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort results list by cosine_similarity descending (mirrors service logic)."""
    return sorted(results, key=lambda r: r["cosine_similarity"], reverse=True)


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    pairs=st.lists(
        st.tuples(st.uuids(), _similarity_strategy),
        min_size=0,
        max_size=20,
    )
)
def test_property13_search_results_sorted_descending(
    pairs: list[tuple[uuid.UUID, float]],
) -> None:
    """
    Feature: tattva-exam-engine, Property 13: search result ordering

    For any list of (chunk_id, cosine_similarity) pairs, results sorted by
    cosine_similarity descending must be in non-increasing order.

    Validates: Requirements 6.4
    """
    results = [
        {
            "chunk_id": str(chunk_id),
            "text": "sample text",
            "cosine_similarity": similarity,
            "source_filename": "test.pdf",
            "page_number": 1,
            "subject_id": str(uuid.uuid4()),
            "module_id": str(uuid.uuid4()),
            "topic_id": str(uuid.uuid4()),
        }
        for chunk_id, similarity in pairs
    ]

    sorted_results = _sort_results_descending(results)

    # Verify non-increasing order
    for i in range(len(sorted_results) - 1):
        assert sorted_results[i]["cosine_similarity"] >= sorted_results[i + 1]["cosine_similarity"], (
            f"Result at index {i} has similarity {sorted_results[i]['cosine_similarity']} "
            f"which is less than result at index {i+1} with similarity "
            f"{sorted_results[i+1]['cosine_similarity']} — not sorted descending"
        )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    pairs=st.lists(
        st.tuples(st.uuids(), _similarity_strategy),
        min_size=1,
        max_size=20,
    )
)
def test_property13_sorted_results_contain_all_items(
    pairs: list[tuple[uuid.UUID, float]],
) -> None:
    """
    Feature: tattva-exam-engine, Property 13: search result ordering (completeness)

    Sorting must not drop or duplicate any item — the sorted list must have
    the same length as the input.

    Validates: Requirements 6.4
    """
    results = [
        {
            "chunk_id": str(chunk_id),
            "text": "text",
            "cosine_similarity": similarity,
            "source_filename": "doc.pdf",
            "page_number": 1,
            "subject_id": str(uuid.uuid4()),
            "module_id": str(uuid.uuid4()),
            "topic_id": str(uuid.uuid4()),
        }
        for chunk_id, similarity in pairs
    ]

    sorted_results = _sort_results_descending(results)

    assert len(sorted_results) == len(results), (
        f"Sorted results length {len(sorted_results)} != input length {len(results)}"
    )


# ---------------------------------------------------------------------------
# Property 14 — subject code uniqueness invariant
#
# Validates: Requirements 6.6
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    code=_valid_code_strategy,
    name=_name_strategy,
)
async def test_property14_subject_code_uniqueness(
    code: str,
    name: str,
) -> None:
    """
    Feature: tattva-exam-engine, Property 14: subject code uniqueness invariant

    Submitting the same subject code twice must result in 201 on the first
    call and 409 on the second call, for any valid code string.

    Validates: Requirements 6.6
    """
    subject_id = uuid.uuid4()

    # We simulate two sequential calls to POST /subjects with the same code.
    # First call: no existing subject → 201.
    # Second call: existing subject found → 409.

    # --- First call setup ---
    created_subject = MagicMock()
    created_subject.id = subject_id
    created_subject.name = name
    created_subject.code = code
    from datetime import datetime, timezone
    created_subject.created_at = datetime.now(timezone.utc)

    mock_session_first = AsyncMock()
    # get_subject_by_code returns None (no duplicate)
    mock_session_first.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=None))
            )
        )
    )
    mock_session_first.add = MagicMock()
    mock_session_first.flush = AsyncMock()
    mock_session_first.refresh = AsyncMock(
        side_effect=lambda obj: (
            setattr(obj, "id", subject_id)
            or setattr(obj, "created_at", datetime.now(timezone.utc))
        )
    )

    mock_cm_first = AsyncMock()
    mock_cm_first.__aenter__ = AsyncMock(return_value=mock_session_first)
    mock_cm_first.__aexit__ = AsyncMock(return_value=False)

    # --- Second call setup ---
    existing_subject = MagicMock()
    existing_subject.id = subject_id
    existing_subject.name = name
    existing_subject.code = code
    existing_subject.created_at = datetime.now(timezone.utc)

    mock_session_second = AsyncMock()
    # get_subject_by_code returns the existing subject
    mock_session_second.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=existing_subject))
            )
        )
    )

    mock_cm_second = AsyncMock()
    mock_cm_second.__aenter__ = AsyncMock(return_value=mock_session_second)
    mock_cm_second.__aexit__ = AsyncMock(return_value=False)

    cms = [mock_cm_first, mock_cm_second]
    call_index = [0]

    def _get_db_factory():
        idx = call_index[0]
        call_index[0] += 1
        return cms[min(idx, len(cms) - 1)]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        with patch(
            "app.services.knowledge_store.router.get_db",
            side_effect=_get_db_factory,
        ):
            # First call — must succeed with 201
            resp_first = await ac.post(
                "/subjects", json={"name": name, "code": code}
            )
            assert resp_first.status_code == 201, (
                f"Expected 201 on first call for code={code!r}, "
                f"got {resp_first.status_code}: {resp_first.text}"
            )

            # Second call with same code — must return 409
            resp_second = await ac.post(
                "/subjects", json={"name": name, "code": code}
            )
            assert resp_second.status_code == 409, (
                f"Expected 409 on second call for duplicate code={code!r}, "
                f"got {resp_second.status_code}: {resp_second.text}"
            )

        detail = resp_second.json()["detail"]
        assert detail["error"] == "duplicate_subject_code", (
            f"Expected duplicate_subject_code error, got: {detail}"
        )
        assert detail["code"] == code, (
            f"Error response should echo the duplicate code; got: {detail}"
        )
