"""
Mock Exam Paper Assembler Service.

Responsibilities:
  - Parse question_type_distribution string (e.g. "2×10mark + 4×6mark + 4×2mark")
  - Fetch PYQs for a subject with topic_importance join
  - Rank questions by topic_importance (frequency_count) descending, ties by most
    recent year; uniform random if all scores are 0
  - Build paper greedily until total_marks_target reached
  - Report warnings for unsatisfied question types (insufficient bank)
  - Return assembled questions ordered by marks descending with topic_tag and marks

Mark-range mapping (per spec):
  - "10mark" → questions with marks >= 8
  - "6mark"  → questions with marks in [4, 7]
  - "2mark"  → questions with marks in [1, 3]
  - Any other N → questions with marks == N (exact match fallback)
"""

from __future__ import annotations

import random
import re
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Distribution parser
# ---------------------------------------------------------------------------

# Matches patterns like: "2×10mark" or "2x10mark" or "2 × 10mark" etc.
_DIST_ITEM_RE = re.compile(
    r"(\d+)\s*[×x]\s*(\d+)\s*mark",
    re.IGNORECASE,
)


def parse_question_type_distribution(
    distribution_str: str,
) -> list[tuple[int, int]]:
    """
    Parse a question_type_distribution string into a list of (count, marks) tuples.

    Examples:
      "2×10mark + 4×6mark + 4×2mark" → [(2, 10), (4, 6), (4, 2)]
      "3x5mark+2x10mark"              → [(3, 5), (2, 10)]
      "1 × 15mark"                    → [(1, 15)]

    Returns an empty list if no valid items are found.
    """
    items: list[tuple[int, int]] = []
    for match in _DIST_ITEM_RE.finditer(distribution_str):
        count = int(match.group(1))
        marks = int(match.group(2))
        if count > 0 and marks > 0:
            items.append((count, marks))
    return items


# ---------------------------------------------------------------------------
# Mark-range matching helper
# ---------------------------------------------------------------------------

def _marks_match(question_marks: int, mark_type: int) -> bool:
    """
    Determine if a question's marks value falls within the mark-type range.

    Range mapping:
      - mark_type == 10  → question_marks >= 8
      - mark_type == 6   → 4 <= question_marks <= 7
      - mark_type == 2   → 1 <= question_marks <= 3
      - any other value  → exact match (question_marks == mark_type)
    """
    if mark_type == 10:
        return question_marks >= 8
    elif mark_type == 6:
        return 4 <= question_marks <= 7
    elif mark_type == 2:
        return 1 <= question_marks <= 3
    else:
        return question_marks == mark_type


# ---------------------------------------------------------------------------
# SQL to fetch PYQs with their topic importance
# ---------------------------------------------------------------------------

_FETCH_PYQS_SQL = text(
    """
    SELECT
        p.id          AS id,
        p.year        AS year,
        p.question_text AS question_text,
        p.marks       AS marks,
        p.topic_id    AS topic_id,
        t.name        AS topic_tag,
        COALESCE(ti.frequency_count, 0) AS frequency_count
    FROM pyqs p
    LEFT JOIN topics t ON t.id = p.topic_id
    LEFT JOIN topic_importance ti ON ti.topic_id = p.topic_id
    WHERE p.subject_id = :subject_id
    ORDER BY frequency_count DESC, p.year DESC
    """
)


async def _fetch_pyqs_for_subject(
    session: AsyncSession,
    subject_id: uuid.UUID,
) -> list[dict]:
    """
    Fetch all PYQs for a subject, joined with topic name and importance score.

    Returns a list of dicts with keys:
      id, year, question_text, marks, topic_id, topic_tag, frequency_count
    """
    result = await session.execute(
        _FETCH_PYQS_SQL, {"subject_id": str(subject_id)}
    )
    rows = result.fetchall()
    return [
        {
            "id": str(row.id),
            "year": row.year,
            "question_text": row.question_text,
            "marks": row.marks,
            "topic_id": str(row.topic_id) if row.topic_id else None,
            # topic_tag: use topic name if available; fall back to str(topic_id)
            # or "Unmatched" if no topic at all
            "topic_tag": (
                row.topic_tag
                if row.topic_tag
                else (str(row.topic_id) if row.topic_id else "Unmatched")
            ),
            "frequency_count": row.frequency_count,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Core assembly logic (pure function — testable without DB)
# ---------------------------------------------------------------------------


def assemble_paper(
    questions: list[dict],
    total_marks_target: int,
    distribution: list[tuple[int, int]],
) -> dict:
    """
    Assemble a mock exam paper from a list of candidate questions.

    Args:
        questions: List of question dicts with keys:
            id, year, question_text, marks, topic_id, topic_tag, frequency_count
        total_marks_target: Positive integer — stop adding questions once this is hit.
        distribution: List of (count, mark_type) tuples from parse_question_type_distribution.
            mark_type is mapped to a marks range via _marks_match().

    Selection order:
      1. Sort by frequency_count DESC, then year DESC.
      2. If ALL frequency_counts are 0, shuffle randomly.

    Build logic:
      - For each (count, mark_type) in distribution, pick up to <count> questions
        matching the mark_type range, chosen from the importance-ordered pool.
      - After satisfying the distribution (or exhausting it), fill any remaining
        capacity from the unselected pool until total_marks_target is reached.
      - Stop as soon as total_marks >= total_marks_target.

    Insufficient bank:
      - If a distribution slot cannot be fully satisfied due to bank shortage,
        record a warning. Stopping early due to marks target is NOT a warning.

    Returns:
        {
            "questions": [{id, year, question_text, marks, topic_tag, topic_id}],
            "total_marks": int,
            "warnings": [str],
        }
    """
    warnings: list[str] = []

    # --- Determine ordering ---
    all_zero = all(q["frequency_count"] == 0 for q in questions)

    if all_zero:
        # Uniform random order
        ordered = list(questions)
        random.shuffle(ordered)
    else:
        # Rank by frequency_count DESC, then year DESC
        ordered = sorted(
            questions,
            key=lambda q: (q["frequency_count"], q["year"]),
            reverse=True,
        )

    # Build a lookup: marks_value → ordered list of candidate questions
    # We'll consume them greedily.
    # Use a set to track already-selected question ids.
    selected_ids: set[str] = set()
    selected: list[dict] = []
    total_marks = 0

    # --- Phase 1: satisfy distribution ---
    for (count, mark_type) in distribution:
        # Candidates for this slot: questions matching the mark_type range,
        # not yet selected, ordered by importance.
        candidates = [
            q for q in ordered
            if _marks_match(q["marks"], mark_type) and q["id"] not in selected_ids
        ]
        available = len(candidates)

        # How many can we actually pick (also respecting marks target)?
        picked = 0
        for q in candidates:
            if total_marks >= total_marks_target:
                break
            if picked >= count:
                break
            selected.append(q)
            selected_ids.add(q["id"])
            total_marks += q["marks"]
            picked += 1

        if picked < count:
            # Check if we stopped because of marks target vs. insufficient bank
            remaining_capacity = total_marks < total_marks_target
            if remaining_capacity and available < count:
                warnings.append(
                    f"Could not satisfy {count}×{mark_type}mark: "
                    f"only {available} available"
                )
            # If we stopped because marks target was reached, that's fine — no warning.

        if total_marks >= total_marks_target:
            break

    # --- Phase 2: fill remaining capacity from leftover pool ---
    if total_marks < total_marks_target:
        leftovers = [q for q in ordered if q["id"] not in selected_ids]
        for q in leftovers:
            if total_marks >= total_marks_target:
                break
            selected.append(q)
            selected_ids.add(q["id"])
            total_marks += q["marks"]

    # --- Return: ordered by marks descending ---
    final_questions = sorted(selected, key=lambda q: q["marks"], reverse=True)

    return {
        "questions": [
            {
                "id": q["id"],
                "year": q["year"],
                "question_text": q["question_text"],
                "marks": q["marks"],
                "topic_tag": q["topic_tag"],
                "topic_id": q["topic_id"],
            }
            for q in final_questions
        ],
        "total_marks": total_marks,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Public entry point — calls DB then assembly
# ---------------------------------------------------------------------------


async def build_mock_paper(
    session: AsyncSession,
    subject_id: uuid.UUID,
    total_marks_target: int,
    question_type_distribution: str,
) -> dict:
    """
    Assemble a mock exam paper for the given subject.

    1. Parse the distribution string.
    2. Fetch candidate PYQs from the DB (joined with topic_importance).
    3. Call assemble_paper() and return the result.

    Returns:
        {
            "questions": [{id, year, question_text, marks, topic_tag, topic_id}],
            "total_marks": int,
            "warnings": [str],
        }
    """
    distribution = parse_question_type_distribution(question_type_distribution)
    questions = await _fetch_pyqs_for_subject(session, subject_id)
    return assemble_paper(questions, total_marks_target, distribution)
