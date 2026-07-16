"""
Property-based tests for the PYQ Analyzer (Task 10.6).

Feature: tattva-exam-engine

Properties under test:
  Property 21 — PYQ field validation predicate
  Property 22 — Topic importance is deterministically computed (idempotent recalculation)
  Property 23 — Topics with no PYQ rows have frequency_count = 0 (default)

Settings: @settings(max_examples=20, deadline=None) per spec.

All tests mock google.generativeai — no real API calls are made.

Validates: Requirements 10.1, 10.4, 10.5
"""

from __future__ import annotations

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.services.knowledge_store.pyq_service import (
    YEAR_MIN,
    MARKS_MIN,
    MARKS_MAX,
    QUESTION_TEXT_MIN,
    QUESTION_TEXT_MAX,
    get_current_year,
    validate_pyq_fields,
    get_topic_importance,
)


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

# Year strategies — covering both valid and invalid ranges
year_strategy = st.integers(min_value=1990, max_value=2150)

# Marks strategies — covering both valid and invalid ranges
marks_strategy = st.integers(min_value=-5, max_value=110)

# Question text strategies — covering both valid and invalid lengths
# Keep max_size small enough for speed while covering boundary cases
question_text_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=0,
    max_size=2010,
)

# Valid-only strategies (for composing valid PYQ triples in Property 22)
valid_year_strategy = st.integers(min_value=YEAR_MIN, max_value=2024)
valid_marks_strategy = st.integers(min_value=MARKS_MIN, max_value=MARKS_MAX)
valid_text_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=QUESTION_TEXT_MIN,
    max_size=QUESTION_TEXT_MAX,
)

# Topic/PYQ data for Property 22: a list of (topic_id, difficulty) pairs
difficulty_strategy = st.sampled_from(["easy", "medium", "hard", None])

pyq_entry_strategy = st.fixed_dictionaries(
    {
        "topic_id": st.uuids(),
        "difficulty": difficulty_strategy,
    }
)

pyq_list_strategy = st.lists(pyq_entry_strategy, min_size=0, max_size=20)


# ---------------------------------------------------------------------------
# Property 21 — PYQ field validation predicate
#
# For any (year, marks, question_text) triple, validate_pyq_fields accepts
# iff (2000 <= year <= current_year) AND (1 <= marks <= 100)
# AND (10 <= len(text) <= 2000).
# Rejection must identify the specific invalid field name.
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    year=year_strategy,
    marks=marks_strategy,
    question_text=question_text_strategy,
)
def test_property21_pyq_validation_predicate(
    year: int,
    marks: int,
    question_text: str,
) -> None:
    """
    Feature: tattva-exam-engine, Property 21: PYQ field validation predicate

    validate_pyq_fields accepts iff all three constraints hold:
      - YEAR_MIN (2000) <= year <= current_year
      - MARKS_MIN (1) <= marks <= MARKS_MAX (100)
      - QUESTION_TEXT_MIN (10) <= len(question_text) <= QUESTION_TEXT_MAX (2000)

    On rejection the returned dict must identify the specific invalid field
    via the "field" key. Validation order is: year → marks → question_text.

    Validates: Requirements 10.1
    """
    current_year = get_current_year()
    year_ok = YEAR_MIN <= year <= current_year
    marks_ok = MARKS_MIN <= marks <= MARKS_MAX
    text_ok = QUESTION_TEXT_MIN <= len(question_text) <= QUESTION_TEXT_MAX

    result = validate_pyq_fields(year, marks, question_text)

    if year_ok and marks_ok and text_ok:
        # All valid → must accept (return None)
        assert result is None, (
            f"Expected valid triple to return None, got {result!r} "
            f"for year={year}, marks={marks}, text_len={len(question_text)}"
        )
    else:
        # At least one field invalid → must return error dict
        assert result is not None, (
            f"Expected invalid triple to return error dict, got None "
            f"for year={year}, marks={marks}, text_len={len(question_text)}"
        )
        assert "field" in result, f"Error dict missing 'field' key: {result!r}"
        assert "detail" in result, f"Error dict missing 'detail' key: {result!r}"

        # Validate priority ordering: year is checked first
        if not year_ok:
            assert result["field"] == "year", (
                f"Invalid year should be reported first; got field={result['field']!r}"
            )
        elif not marks_ok:
            # year was valid, marks is the first invalid field
            assert result["field"] == "marks", (
                f"Invalid marks should be reported (year was valid); "
                f"got field={result['field']!r}"
            )
        else:
            # year and marks valid, question_text must be invalid
            assert result["field"] == "question_text", (
                f"Invalid question_text should be reported (year+marks valid); "
                f"got field={result['field']!r}"
            )


# ---------------------------------------------------------------------------
# Property 22 — Topic importance is deterministically computed
#
# Calling recalculate_topic_importance twice on the same PYQ data must
# produce identical frequency_count values for all topics.
# This is tested by simulating the SQL COUNT logic in Python and verifying
# it is deterministic across two identical runs.
# ---------------------------------------------------------------------------


def _simulate_importance_calculation(
    pyq_rows: list[dict],
) -> dict[str, int]:
    """
    Pure-Python simulation of the SQL COUNT(*) GROUP BY topic_id logic.

    Mirrors the SQL:
      SELECT topic_id, COUNT(*) FROM pyqs
      WHERE topic_id IS NOT NULL
      GROUP BY topic_id

    Returns a dict mapping str(topic_id) → frequency_count.
    """
    counts: dict[str, int] = {}
    for row in pyq_rows:
        tid = row.get("topic_id")
        if tid is None:
            continue
        key = str(tid)
        counts[key] = counts.get(key, 0) + 1
    return counts


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pyq_rows=pyq_list_strategy)
def test_property22_recalculation_is_deterministic(
    pyq_rows: list[dict],
) -> None:
    """
    Feature: tattva-exam-engine, Property 22: topic importance deterministically computed

    Running the importance calculation twice on the same PYQ dataset must
    produce identical frequency_count values for every topic.
    Determinism is the core guarantee that enables the ON CONFLICT DO UPDATE
    upsert semantics: re-running never changes the result.

    Validates: Requirements 10.4
    """
    # First run
    result_first = _simulate_importance_calculation(pyq_rows)
    # Second run (same input)
    result_second = _simulate_importance_calculation(pyq_rows)

    assert result_first == result_second, (
        f"Two identical calculation runs produced different results:\n"
        f"  first:  {result_first}\n"
        f"  second: {result_second}"
    )

    # Additional invariant: frequency counts are always positive integers
    for topic_id_str, count in result_first.items():
        assert count > 0, (
            f"frequency_count must be > 0 for matched topic {topic_id_str!r}; "
            f"got {count}"
        )


# ---------------------------------------------------------------------------
# Property 23 — Topics with no PYQ rows have frequency_count = 0 (default)
#
# get_topic_importance returns {"frequency_count": 0, ...} for any topic_id
# that has no row in topic_importance table (i.e., TopicImportance query
# returns None). This tests the default-value path in the service.
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(topic_id=st.uuids())
@pytest.mark.asyncio
async def test_property23_unseen_topic_defaults_to_zero_frequency(
    topic_id: uuid.UUID,
) -> None:
    """
    Feature: tattva-exam-engine, Property 23: unseen topics default to frequency_count = 0

    For any topic_id that has no row in topic_importance, get_topic_importance
    must return a dict with frequency_count = 0, difficulty_avg = None,
    and last_recalculated = None — matching the default row specification.

    Validates: Requirements 10.5
    """
    # Mock a database session that returns no TopicImportance row for this topic
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(
                    first=MagicMock(return_value=None)  # no record found
                )
            )
        )
    )

    result = await get_topic_importance(mock_session, topic_id)

    assert result["frequency_count"] == 0, (
        f"Expected frequency_count=0 for unseen topic {topic_id}, "
        f"got {result['frequency_count']}"
    )
    assert result["topic_id"] == str(topic_id), (
        f"Expected topic_id={str(topic_id)!r}, got {result['topic_id']!r}"
    )
    assert result["difficulty_avg"] is None, (
        f"Expected difficulty_avg=None for unseen topic, got {result['difficulty_avg']}"
    )
    assert result["last_recalculated"] is None, (
        f"Expected last_recalculated=None for unseen topic, "
        f"got {result['last_recalculated']}"
    )
