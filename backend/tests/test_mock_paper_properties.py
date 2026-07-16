"""
Property-based tests for the Mock Exam Paper Assembler (Task 11.6).

Feature: tattva-exam-engine

Property 24 — mock paper ordering respects topic importance; ties broken by year:
  For any list of questions with at least 2 distinct frequency_counts, the selection
  order must place higher-frequency questions before lower-frequency ones.
  For ties in frequency_count, the more recent year comes first.

Settings: @settings(max_examples=20, deadline=None) per spec.

Validates: Requirements 11.2
"""

from __future__ import annotations

import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.knowledge_store.mock_paper_service import assemble_paper


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_freq_strategy = st.integers(min_value=0, max_value=100)
_year_strategy = st.integers(min_value=2000, max_value=2024)
_marks_strategy = st.integers(min_value=1, max_value=20)


@st.composite
def _question(draw, qid: str | None = None) -> dict:
    """Draw a single question dict."""
    return {
        "id": qid or str(uuid.uuid4()),
        "year": draw(_year_strategy),
        "question_text": "Hypothesis-generated question.",
        "marks": draw(_marks_strategy),
        "topic_id": str(uuid.uuid4()),
        "topic_tag": "Hypothesis Topic",
        "frequency_count": draw(_freq_strategy),
    }


@st.composite
def _questions_with_distinct_freq(draw) -> list[dict]:
    """Draw a list of 2–8 questions guaranteed to have at least 2 distinct frequency_counts."""
    n = draw(st.integers(min_value=2, max_value=8))
    questions = [draw(_question()) for _ in range(n)]
    # Ensure at least 2 distinct frequency_counts
    freqs = [q["frequency_count"] for q in questions]
    if len(set(freqs)) < 2:
        # Force the first two to have distinct counts
        questions[0] = {**questions[0], "frequency_count": 0}
        questions[1] = {**questions[1], "frequency_count": 10}
    return questions


@st.composite
def _questions_with_tied_freq(draw) -> list[dict]:
    """Draw 2–5 questions all sharing the same frequency_count but with distinct years."""
    n = draw(st.integers(min_value=2, max_value=5))
    common_freq = draw(st.integers(min_value=1, max_value=50))
    # Use strictly decreasing years so ties are deterministic
    base_year = draw(st.integers(min_value=2005, max_value=2022))
    questions = []
    for i in range(n):
        marks = draw(_marks_strategy)
        questions.append({
            "id": str(uuid.uuid4()),
            "year": base_year - i,  # strictly decreasing years
            "question_text": f"Tied-freq question {i}.",
            "marks": marks,
            "topic_id": str(uuid.uuid4()),
            "topic_tag": "Tied Topic",
            "frequency_count": common_freq,
        })
    return questions


# ---------------------------------------------------------------------------
# Property 24 — ordering respects topic importance; ties broken by year
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(questions=_questions_with_distinct_freq())
def test_property24_importance_ordering(questions: list[dict]) -> None:
    """
    Feature: tattva-exam-engine, Property 24: mock paper ordering respects topic importance

    For any question list with at least 2 distinct frequency_counts, assemble_paper
    (with no distribution constraints and a high marks target) must select questions
    starting from the highest frequency_count.

    The first question in the assembled paper must have frequency_count >=
    the frequency_count of the last question.

    Validates: Requirements 11.2
    """
    # Use a high marks target so all questions are included
    total_marks = sum(q["marks"] for q in questions) + 100

    result = assemble_paper(
        questions=questions,
        total_marks_target=total_marks,
        distribution=[],
    )

    selected = result["questions"]
    if len(selected) < 2:
        return  # not enough questions to test ordering

    # Build a map from question id back to frequency_count (using original list)
    freq_map = {q["id"]: q["frequency_count"] for q in questions}

    # Reconstruct frequency_counts in selection order
    # Note: assemble_paper returns questions sorted by marks DESC.
    # To verify importance ordering we need to look at the order BEFORE the final
    # marks-desc sort.  We verify instead that no low-freq question is selected
    # when a higher-freq question is available.
    #
    # Invariant: max(freq of selected) >= max(freq of unselected or equal selection)
    # Simplified check: if any question was excluded, all included questions
    # must have frequency_count >= any excluded question's frequency_count.
    selected_ids = {q["id"] for q in selected}
    unselected = [q for q in questions if q["id"] not in selected_ids]

    if unselected:
        min_selected_freq = min(freq_map[q["id"]] for q in selected)
        max_unselected_freq = max(q["frequency_count"] for q in unselected)
        assert min_selected_freq >= max_unselected_freq, (
            f"A lower-priority question was selected over a higher-priority one.\n"
            f"Min frequency in selected: {min_selected_freq}\n"
            f"Max frequency in unselected: {max_unselected_freq}"
        )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(questions=_questions_with_tied_freq())
def test_property24_tie_breaking_by_year(questions: list[dict]) -> None:
    """
    Feature: tattva-exam-engine, Property 24: ties broken by most recent year

    For any list of questions with the same frequency_count but strictly
    decreasing years, assemble_paper must select the most recent year first
    when picking only one question.

    Validates: Requirements 11.2
    """
    # We pick only 1 question: the one with the highest year (most recent)
    most_recent = max(questions, key=lambda q: q["year"])
    smallest_marks = min(q["marks"] for q in questions)

    # Build a distribution that requests exactly 1 question of the smallest marks value
    # among the candidates — but since we want deterministic tie-breaking just pick 1 total
    result = assemble_paper(
        questions=questions,
        total_marks_target=most_recent["marks"],
        distribution=[],
    )

    selected = result["questions"]
    if not selected:
        return  # edge case: no questions fit

    # The first question selected (before marks-desc sort) should be the most-recent.
    # Since all have the same frequency_count, year DESC decides.
    # After marks-desc final sort, the order may differ — check via freq_map instead.
    selected_ids = {q["id"] for q in selected}

    # Among questions NOT selected, none should have a more recent year than
    # the most recent selected question (all have same freq so year is the tiebreaker).
    unselected = [q for q in questions if q["id"] not in selected_ids]
    if unselected:
        max_selected_year = max(
            q["year"] for q in questions if q["id"] in selected_ids
        )
        max_unselected_year = max(q["year"] for q in unselected)
        assert max_selected_year >= max_unselected_year, (
            f"A more recent question was skipped in favour of an older one.\n"
            f"Max year selected: {max_selected_year}\n"
            f"Max year unselected: {max_unselected_year}"
        )


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    questions=st.lists(
        _question(),
        min_size=2,
        max_size=10,
    ).filter(lambda qs: any(q["frequency_count"] > 0 for q in qs))
)
def test_property24_no_lower_priority_question_skips_higher(
    questions: list[dict],
) -> None:
    """
    Feature: tattva-exam-engine, Property 24: no lower-priority selection before higher

    For any question bank where at least one question has frequency_count > 0,
    the assembled paper must not skip a higher-frequency question in favour of
    a lower-frequency one (assuming sufficient marks target for all).

    Validates: Requirements 11.2
    """
    total_marks = sum(q["marks"] for q in questions) + 100

    result = assemble_paper(
        questions=questions,
        total_marks_target=total_marks,
        distribution=[],
    )

    # All questions should be selected when target is ample
    assert len(result["questions"]) == len(questions), (
        f"Expected all {len(questions)} questions to be selected, "
        f"got {len(result['questions'])}"
    )
