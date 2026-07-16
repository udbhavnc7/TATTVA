"""
Syllabus Coverage Tracker Service — Task 9.

Computes coverage metrics by aggregating note confidence badges across all
topics in the knowledge store.

Coverage percentage formula:
  round((grounded_count / total_topics) * 100)  where total_topics > 0
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Note, Topic


async def get_coverage_metrics(session: AsyncSession) -> dict[str, Any]:
    """
    Compute syllabus coverage metrics across all topics.

    Returns
    -------
    dict with keys:
      grounded_count     : int  — topics with at least one 'grounded' note
      partial_count      : int  — topics with 'partial' but no 'grounded' note
      needs_review_count : int  — topics with only 'needs_review' notes
      no_notes_count     : int  — topics with no generated notes at all
      total_topics       : int  — total topics in the knowledge store
      coverage_percentage: int  — round((grounded_count / total_topics) * 100)
      topics             : list — per-topic badge status for the syllabus outline
    """
    # Fetch all topics
    topics_result = await session.execute(select(Topic))
    all_topics = topics_result.scalars().all()
    total_topics = len(all_topics)

    if total_topics == 0:
        return {
            "grounded_count": 0,
            "partial_count": 0,
            "needs_review_count": 0,
            "no_notes_count": 0,
            "total_topics": 0,
            "coverage_percentage": 0,
            "topics": [],
        }

    # For each topic, determine the best badge from its notes
    # Best badge order: grounded > partial > needs_review > none
    _BADGE_RANK = {"grounded": 3, "partial": 2, "needs_review": 1}

    notes_result = await session.execute(
        select(Note.topic_id, Note.confidence)
    )
    note_rows = notes_result.all()

    # Build per-topic best badge map
    topic_badge: dict[str, str] = {}
    for topic_id, confidence in note_rows:
        tid = str(topic_id)
        current_rank = _BADGE_RANK.get(topic_badge.get(tid, ""), 0)
        new_rank = _BADGE_RANK.get(confidence, 0)
        if new_rank > current_rank:
            topic_badge[tid] = confidence

    # Count badges
    grounded_count = sum(1 for b in topic_badge.values() if b == "grounded")
    partial_count = sum(1 for b in topic_badge.values() if b == "partial")
    needs_review_count = sum(1 for b in topic_badge.values() if b == "needs_review")
    no_notes_count = total_topics - len(topic_badge)

    coverage_percentage = round((grounded_count / total_topics) * 100) if total_topics > 0 else 0

    # Build per-topic list for syllabus outline UI
    topics_list = []
    for topic in all_topics:
        tid = str(topic.id)
        badge = topic_badge.get(tid, None)  # None = no notes
        topics_list.append({
            "topic_id": tid,
            "topic_name": topic.name,
            "module_id": str(topic.module_id),
            "badge": badge,
        })

    return {
        "grounded_count": grounded_count,
        "partial_count": partial_count,
        "needs_review_count": needs_review_count,
        "no_notes_count": no_notes_count,
        "total_topics": total_topics,
        "coverage_percentage": coverage_percentage,
        "topics": topics_list,
    }
