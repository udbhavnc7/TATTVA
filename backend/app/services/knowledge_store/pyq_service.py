"""
PYQ Analyzer Service — business logic layer.

Responsibilities:
  - Input validation for POST /pyqs
  - LLM topic matching via prompt C5 (Gemini Flash)
  - Storing difficulty, difficulty_note, secondary_topics per PYQ
  - Deterministic SQL COUNT(*) GROUP BY topic_id upsert into topic_importance
  - GET /pyqs with filters
  - GET /topics/{id}/importance
"""

from __future__ import annotations

import datetime
import os
import uuid
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Pyq, TopicImportance, Topic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YEAR_MIN = 2000
MARKS_MIN = 1
MARKS_MAX = 100
QUESTION_TEXT_MIN = 10
QUESTION_TEXT_MAX = 2000

VALID_DIFFICULTIES = {"easy", "medium", "hard"}

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def get_current_year() -> int:
    """Return the current calendar year."""
    return datetime.datetime.now().year


def validate_pyq_fields(
    year: int,
    marks: int,
    question_text: str,
) -> Optional[dict[str, str]]:
    """
    Validate PYQ fields per the acceptance criteria.

    Returns None if all fields are valid.
    Returns a dict {"field": "<fieldname>", "detail": "<reason>"} for the
    first invalid field found (priority: year → marks → question_text).
    """
    current_year = get_current_year()

    if not (YEAR_MIN <= year <= current_year):
        return {
            "field": "year",
            "detail": f"year must be between {YEAR_MIN} and {current_year} inclusive; got {year}",
        }

    if not (MARKS_MIN <= marks <= MARKS_MAX):
        return {
            "field": "marks",
            "detail": f"marks must be between {MARKS_MIN} and {MARKS_MAX} inclusive; got {marks}",
        }

    q_len = len(question_text)
    if not (QUESTION_TEXT_MIN <= q_len <= QUESTION_TEXT_MAX):
        return {
            "field": "question_text",
            "detail": (
                f"question_text must be between {QUESTION_TEXT_MIN} and "
                f"{QUESTION_TEXT_MAX} characters inclusive; got {q_len}"
            ),
        }

    return None


# ---------------------------------------------------------------------------
# LLM topic matching (prompt C5)
# ---------------------------------------------------------------------------

_C5_PROMPT_TEMPLATE = """\
You are a topic-matching assistant for an engineering exam preparation system.

Given a past year question and a list of topics, identify the best matching topic.

Question: {question_text}

Available topics (id | name):
{topic_list}

Rules:
1. Return JSON with exactly these fields:
   - "matched_topic_id": UUID string of the best matching topic, or null if no confident match
   - "confidence": "high", "medium", or "low"
   - "difficulty": "easy", "medium", or "hard" (estimated difficulty of this question)
   - "difficulty_note": brief explanation of difficulty (max 200 characters)
2. Only set matched_topic_id to a real topic ID if confidence is "high" or "medium".
3. If confidence is "low" or no topic matches, set matched_topic_id to null.
4. Respond ONLY with valid JSON, no extra text.

JSON response:
"""


def _call_llm_for_topic_match(question_text: str, topics: list[dict]) -> dict:
    """
    Call Gemini Flash to match a PYQ to a topic.

    Returns a dict with keys:
      matched_topic_id (str | None), confidence (str),
      difficulty (str), difficulty_note (str)

    Raises RuntimeError on LLM failure.
    """
    import json
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key:
        genai.configure(api_key=api_key)

    topic_list_str = "\n".join(
        f"{t['id']} | {t['name']}" for t in topics
    )

    prompt = _C5_PROMPT_TEMPLATE.format(
        question_text=question_text,
        topic_list=topic_list_str if topic_list_str else "(no topics available)",
    )

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()

    result = json.loads(raw)

    # Normalise fields
    matched_id = result.get("matched_topic_id")
    confidence = str(result.get("confidence", "low")).lower()
    difficulty = str(result.get("difficulty", "medium")).lower()
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "medium"
    difficulty_note = str(result.get("difficulty_note", ""))[:200]

    # Only trust the match if confidence is high or medium
    if confidence not in ("high", "medium"):
        matched_id = None

    return {
        "matched_topic_id": matched_id,
        "confidence": confidence,
        "difficulty": difficulty,
        "difficulty_note": difficulty_note,
    }


async def match_topic_for_pyq(
    session: AsyncSession,
    question_text: str,
    subject_id: uuid.UUID,
) -> dict:
    """
    Run LLM topic matching (prompt C5) for a PYQ.

    Fetches all topics for the given subject and calls the LLM.
    Returns a dict with:
      - topic_id: UUID | None
      - is_unmatched: bool
      - difficulty: str
      - difficulty_note: str
    """
    # Fetch topics belonging to this subject (via module → subject chain)
    sql = text(
        """
        SELECT t.id, t.name
        FROM topics t
        JOIN modules m ON m.id = t.module_id
        WHERE m.subject_id = :subject_id
        ORDER BY t.name
        """
    )
    rows = await session.execute(sql, {"subject_id": str(subject_id)})
    topics = [{"id": str(r[0]), "name": r[1]} for r in rows.fetchall()]

    if not topics:
        return {
            "topic_id": None,
            "is_unmatched": True,
            "difficulty": "medium",
            "difficulty_note": "No topics available for subject.",
        }

    try:
        llm_result = _call_llm_for_topic_match(question_text, topics)
    except Exception:  # noqa: BLE001
        # LLM failure → treat as unmatched
        return {
            "topic_id": None,
            "is_unmatched": True,
            "difficulty": "medium",
            "difficulty_note": "Topic matching failed; marked for manual review.",
        }

    matched_id_str = llm_result.get("matched_topic_id")
    topic_id: Optional[uuid.UUID] = None
    is_unmatched = True

    if matched_id_str:
        try:
            topic_id = uuid.UUID(matched_id_str)
            is_unmatched = False
        except ValueError:
            topic_id = None
            is_unmatched = True

    return {
        "topic_id": topic_id,
        "is_unmatched": is_unmatched,
        "difficulty": llm_result["difficulty"],
        "difficulty_note": llm_result["difficulty_note"],
    }


# ---------------------------------------------------------------------------
# PYQ CRUD
# ---------------------------------------------------------------------------


async def create_pyq(
    session: AsyncSession,
    subject_id: uuid.UUID,
    year: int,
    question_text: str,
    marks: int,
    topic_id: Optional[uuid.UUID],
    is_unmatched: bool,
    difficulty: Optional[str],
    difficulty_note: Optional[str],
    secondary_topics: Optional[list[uuid.UUID]],
) -> Pyq:
    """Insert a new PYQ record and return it."""
    pyq = Pyq(
        subject_id=subject_id,
        year=year,
        question_text=question_text,
        marks=marks,
        topic_id=topic_id,
        is_unmatched=is_unmatched,
        difficulty=difficulty,
        difficulty_note=difficulty_note[:200] if difficulty_note else None,
        secondary_topics=secondary_topics or [],
    )
    session.add(pyq)
    await session.flush()
    await session.refresh(pyq)
    return pyq


async def get_pyqs(
    session: AsyncSession,
    subject_id: Optional[uuid.UUID] = None,
    topic_id: Optional[uuid.UUID] = None,
    is_unmatched: Optional[bool] = None,
) -> list[Pyq]:
    """Return PYQs filtered by optional subject_id, topic_id, is_unmatched."""
    stmt = select(Pyq).order_by(Pyq.year.desc())

    if subject_id is not None:
        stmt = stmt.where(Pyq.subject_id == subject_id)
    if topic_id is not None:
        stmt = stmt.where(Pyq.topic_id == topic_id)
    if is_unmatched is not None:
        stmt = stmt.where(Pyq.is_unmatched == is_unmatched)

    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Recalculate topic importance — deterministic SQL only, NEVER LLM
# ---------------------------------------------------------------------------

_RECALCULATE_SQL = text(
    """
    INSERT INTO topic_importance (topic_id, frequency_count, difficulty_avg, last_recalculated)
    SELECT
        topic_id,
        COUNT(*) AS frequency_count,
        AVG(
            CASE difficulty
                WHEN 'easy'   THEN 1
                WHEN 'medium' THEN 2
                WHEN 'hard'   THEN 3
                ELSE NULL
            END
        ) AS difficulty_avg,
        NOW()
    FROM pyqs
    WHERE topic_id IS NOT NULL
    GROUP BY topic_id
    ON CONFLICT (topic_id) DO UPDATE
        SET frequency_count    = EXCLUDED.frequency_count,
            difficulty_avg     = EXCLUDED.difficulty_avg,
            last_recalculated  = EXCLUDED.last_recalculated
    """
)


async def recalculate_topic_importance(session: AsyncSession) -> int:
    """
    Run the deterministic SQL upsert for topic_importance.

    This function NEVER calls an LLM. Frequency counting is a pure SQL
    COUNT(*) GROUP BY topic_id, as required by the design specification.

    Returns the number of topic rows affected (rowcount may not be reliable
    across all drivers; returns -1 if unavailable).
    """
    result = await session.execute(_RECALCULATE_SQL)
    return result.rowcount if result.rowcount is not None else -1


# ---------------------------------------------------------------------------
# Topic importance query
# ---------------------------------------------------------------------------


async def get_topic_importance(
    session: AsyncSession,
    topic_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Return the topic_importance record for a topic.

    If no record exists, returns a default dict with frequency_count = 0.
    """
    result = await session.execute(
        select(TopicImportance).where(TopicImportance.topic_id == topic_id)
    )
    row = result.scalars().first()

    if row is None:
        return {
            "topic_id": str(topic_id),
            "frequency_count": 0,
            "difficulty_avg": None,
            "last_recalculated": None,
        }

    return {
        "topic_id": str(row.topic_id),
        "frequency_count": row.frequency_count,
        "difficulty_avg": float(row.difficulty_avg) if row.difficulty_avg is not None else None,
        "last_recalculated": row.last_recalculated.isoformat() if row.last_recalculated else None,
    }
