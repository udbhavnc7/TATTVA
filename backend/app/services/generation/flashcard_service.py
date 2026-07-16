"""
Spaced Repetition Flashcard Service — Task 12.

Public API
----------
update_sm2(ease_factor, interval_days, repetitions, recall_score) -> dict
    Pure SM-2 update function. No side effects. Returns updated scheduling state.

generate_flashcards_for_note(session, note_id, topic_id, note_content) -> list[Flashcard]
    Generate 4–6 flashcards from a note using Gemini Flash. Creates and stores
    Flashcard ORM instances with initial SM-2 state (ease_factor=2.5).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Flashcard

# ---------------------------------------------------------------------------
# SM-2 pure function (Task 12.2)
# ---------------------------------------------------------------------------

def update_sm2(
    ease_factor: float,
    interval_days: int,
    repetitions: int,
    recall_score: int,
) -> dict[str, Any]:
    """
    SM-2 algorithm — pure function, no side effects.

    Parameters
    ----------
    ease_factor  : current EF (≥ 1.3, initial = 2.5)
    interval_days: current review interval in days (≥ 1)
    repetitions  : successful review count (≥ 0)
    recall_score : student self-reported quality 0–5

    Returns
    -------
    dict with keys: ease_factor, interval_days, repetitions, next_review_at (UTC datetime)
    """
    if recall_score < 3:  # failed recall — restart
        repetitions = 0
        interval = 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval_days * ease_factor)
        repetitions += 1

    new_ef = ease_factor + (0.1 - (5 - recall_score) * (0.08 + (5 - recall_score) * 0.02))
    new_ef = max(1.3, new_ef)

    next_review_at = datetime.now(timezone.utc) + timedelta(days=interval)

    return {
        "ease_factor": round(new_ef, 4),
        "interval_days": interval,
        "repetitions": repetitions,
        "next_review_at": next_review_at,
    }


# ---------------------------------------------------------------------------
# Flashcard generation prompt
# ---------------------------------------------------------------------------

_FLASHCARD_PROMPT_TEMPLATE = """\
You are creating spaced-repetition flashcards for an engineering exam student.

Given this study note, generate exactly {count} flashcards.

Rules:
- Each flashcard front is ONE focused question derived ONLY from the note.
- Each flashcard back is a concise answer of NO MORE THAN 40 WORDS, ending with a citation in the form (Source: <filename>.pdf, p.<N>).
- Use ONLY facts present in the note.
- Vary the questions to cover different aspects of the note.

Return ONLY a JSON array of objects with keys "front" and "back":
[
  {{"front": "question 1", "back": "answer with citation (Source: ...)"}},
  ...
]

Study note:
{note_content}
"""


def _build_flashcard_prompt(note_content: str, count: int = 5) -> str:
    return _FLASHCARD_PROMPT_TEMPLATE.format(note_content=note_content, count=count)


def _call_gemini_for_flashcards(prompt: str) -> list[dict]:
    """Call Gemini Flash and parse flashcard JSON. Returns list of {front, back} dicts."""
    try:
        import google.generativeai as genai

        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        response = model.generate_content(prompt)
        raw = response.text.strip()
    except Exception as exc:
        raise RuntimeError(f"Gemini Flash call failed: {exc}") from exc

    # Strip markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

    try:
        cards = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse flashcard JSON: {exc}") from exc

    if not isinstance(cards, list):
        raise ValueError("Expected JSON array from flashcard generator")

    return cards


def _truncate_answer(answer: str, max_words: int = 40) -> str:
    """Truncate answer to max_words words, preserving the citation at the end."""
    words = answer.split()
    if len(words) <= max_words:
        return answer

    # Keep as many words as possible while leaving room for the citation
    citation_match = re.search(r"\(Source:[^)]+\)", answer)
    if citation_match:
        citation = citation_match.group(0)
        body = answer[: citation_match.start()].strip()
        body_words = body.split()
        # Reserve words for citation (approximately)
        available = max_words - len(citation.split())
        if available > 0:
            truncated_body = " ".join(body_words[:available])
            return f"{truncated_body} {citation}"
        return citation  # extreme edge case

    return " ".join(words[:max_words])


# ---------------------------------------------------------------------------
# Flashcard generation (Task 12.1)
# ---------------------------------------------------------------------------

async def generate_flashcards_for_note(
    session: AsyncSession,
    note_id: uuid.UUID,
    topic_id: uuid.UUID,
    note_content: str,
) -> list[Flashcard]:
    """
    Generate 4–6 flashcards from *note_content* using Gemini Flash.

    Each flashcard is created with initial SM-2 state:
      ease_factor=2.5, interval_days=1, repetitions=0, next_review_at=now()

    The cards are stored in the database and returned.

    Returns
    -------
    list[Flashcard]
        Between 4 and 6 Flashcard ORM instances (flushed, not committed).
    """
    prompt = _build_flashcard_prompt(note_content, count=5)
    raw_cards = _call_gemini_for_flashcards(prompt)

    # Clamp to 4–6
    raw_cards = raw_cards[:6]
    if len(raw_cards) < 4:
        # Pad with generic question if LLM returned too few
        while len(raw_cards) < 4:
            raw_cards.append(
                {"front": "What is the main concept described in this note?", "back": "(Source: see note)"}
            )

    now = datetime.now(timezone.utc)
    flashcards: list[Flashcard] = []

    for card_data in raw_cards:
        question = str(card_data.get("front", "")).strip()
        answer = _truncate_answer(str(card_data.get("back", "")).strip())

        if not question or not answer:
            continue

        fc = Flashcard(
            topic_id=topic_id,
            note_id=note_id,
            question=question,
            answer=answer,
            source=None,  # source is embedded in the answer citation
            ease_factor=2.5,
            interval_days=1,
            repetitions=0,
            next_review_at=now,
        )
        session.add(fc)
        flashcards.append(fc)

    await session.flush()
    return flashcards


# ---------------------------------------------------------------------------
# Flashcard list query (Task 12.4)
# ---------------------------------------------------------------------------

async def get_flashcards(
    session: AsyncSession,
    topic_id: uuid.UUID | None = None,
    due_only: bool = False,
) -> dict[str, int]:
    """
    Return card_count and due_count for the given filters.

    Parameters
    ----------
    topic_id : filter to this topic (or all topics if None)
    due_only : if True, only count/return cards where next_review_at <= now()
    """
    stmt = select(Flashcard)
    if topic_id is not None:
        stmt = stmt.where(Flashcard.topic_id == topic_id)

    result = await session.execute(stmt)
    all_cards = result.scalars().all()

    now = datetime.now(timezone.utc)
    due_cards = [c for c in all_cards if c.next_review_at <= now]

    return {
        "card_count": len(all_cards),
        "due_count": len(due_cards),
    }


# ---------------------------------------------------------------------------
# Review submission (Task 12.3)
# ---------------------------------------------------------------------------

async def submit_review(
    session: AsyncSession,
    flashcard_id: uuid.UUID,
    recall_score: int,
) -> Flashcard:
    """
    Update a flashcard's SM-2 state after a student review.

    Parameters
    ----------
    session      : active async database session
    flashcard_id : UUID of the flashcard being reviewed
    recall_score : student self-reported quality 0–5

    Returns
    -------
    Flashcard
        The updated Flashcard instance.

    Raises
    ------
    ValueError
        If recall_score is outside [0, 5].
    LookupError
        If no flashcard with the given ID exists.
    """
    if not (0 <= recall_score <= 5):
        raise ValueError(
            f"recall_score must be between 0 and 5 inclusive; got {recall_score}"
        )

    result = await session.execute(
        select(Flashcard).where(Flashcard.id == flashcard_id)
    )
    card: Flashcard | None = result.scalars().first()
    if card is None:
        raise LookupError(f"Flashcard '{flashcard_id}' not found.")

    updated = update_sm2(
        ease_factor=float(card.ease_factor),
        interval_days=int(card.interval_days),
        repetitions=int(card.repetitions),
        recall_score=recall_score,
    )

    card.ease_factor = updated["ease_factor"]
    card.interval_days = updated["interval_days"]
    card.repetitions = updated["repetitions"]
    card.next_review_at = updated["next_review_at"]

    await session.flush()
    return card
