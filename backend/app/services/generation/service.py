"""
Grounded Note Generation Service — Task 7.

Public API
----------
generate_note(session, topic_id, depth, force_regenerate) -> dict | None
    Core generation function. Retrieves top-5 chunks via semantic_search,
    gates on max cosine_similarity >= 0.5, calls Gemini API with depth-tiered
    prompt C2, parses CONFIDENCE line, calls Confidence Validator (Task 8),
    stores note record, and returns { note_id, confidence, content_md }.

    Returns None if generation is refused (similarity gate) — callers interpret
    this as a 422 response.

    Raises GenerationError on LLM failure — callers return 500 and write no note.

validate_note(session, note_id, note_content, cited_chunks) -> str
    Confidence Validator — real second-pass implementation (Task 8).
    Imported from app.services.generation.validator.

get_notes_for_topic(session, topic_id) -> list[dict]
    Return all note records for the topic ordered by (depth, version DESC).

VALID_DEPTHS
    Set of allowed depth strings: {"2mark", "6mark", "10mark"}.

CONFIDENCE_VALUES
    Set of allowed badge strings: {"grounded", "partial", "needs_review"}.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Note, Topic
from app.services.knowledge_store.service import get_topic_by_id, semantic_search
from app.services.generation.validator import validate_note  # noqa: F401 — real impl (Task 8)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_DEPTHS = {"2mark", "6mark", "10mark"}
CONFIDENCE_VALUES = {"grounded", "partial", "needs_review"}

# Cosine similarity threshold below which generation is refused
SIMILARITY_THRESHOLD = 0.5

# Gemini model selection per depth (cheaper flash for 2/6-mark)
_GEMINI_MODEL = {
    "2mark": "gemini-1.5-flash",
    "6mark": "gemini-1.5-flash",
    "10mark": "gemini-1.5-pro",
}

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class GenerationError(Exception):
    """Raised when the LLM call fails; callers must return 500 and write no note."""

    def __init__(self, message: str, reason: str = "llm_failure") -> None:
        super().__init__(message)
        self.reason = reason


class CoverageInsufficient(Exception):
    """Raised when max(cosine_similarity) < 0.5; callers return 422."""


# ---------------------------------------------------------------------------
# Depth-tiered generation prompt (C2)
# ---------------------------------------------------------------------------

_SYSTEM_INSTRUCTION = (
    "You are an expert study note writer for engineering students. "
    "Use ONLY the retrieved context below — do NOT add facts from your own training data. "
    "If the context doesn't fully cover something needed at this depth, say "
    "'Not covered in provided material' instead of filling the gap. "
    "For EVERY paragraph, you MUST append a citation in the form: "
    "(Source: <filename>, p.<page_number>). "
    "The last line of your response MUST be exactly: "
    "CONFIDENCE: grounded|partial|needs_review "
    "(choose one value — no other text on that line)."
)

_DEPTH_INSTRUCTIONS = {
    "2mark": (
        "Write a 2-mark exam answer: 2 to 4 sentences. "
        "Include one crisp definition and a single citation per answer."
    ),
    "6mark": (
        "Write a 6-mark exam answer with three sections: "
        "1) Definition paragraph, "
        "2) Explanation paragraph, "
        "3) Example paragraph. "
        "Each paragraph must have its own (Source: ..., p.N) citation."
    ),
    "10mark": (
        "Write a 10-mark exam answer with all of the following sections: "
        "1) Definition, "
        "2) Three or more sub-points (each a distinct aspect), "
        "3) Worked example, "
        "4) Diagram reference (describe what the diagram would show; use Mermaid syntax if possible), "
        "5) Advantages / Comparison with alternatives. "
        "Every paragraph must have its own (Source: ..., p.N) citation."
    ),
}


def _build_prompt(
    topic_name: str,
    depth: str,
    chunks: list[dict],
) -> str:
    """
    Assemble the full generation prompt (C2) for the given depth.

    Chunks are listed in descending similarity order, each prefixed with
    [Source: {filename}, p.{page}] so the LLM can cite them correctly.
    """
    context_parts: list[str] = []
    for chunk in chunks:
        filename = chunk.get("source_filename", "unknown.pdf")
        page = chunk.get("page_number", 0)
        text = chunk.get("text", "")
        context_parts.append(f"[Source: {filename}, p.{page}]\n{text}")

    context_block = "\n\n---\n\n".join(context_parts)

    depth_instruction = _DEPTH_INSTRUCTIONS[depth]

    return (
        f"{_SYSTEM_INSTRUCTION}\n\n"
        f"Topic: {topic_name}\n"
        f"Depth: {depth}\n"
        f"Instruction: {depth_instruction}\n\n"
        f"Retrieved Context:\n{context_block}\n\n"
        "Generate the study note now:"
    )


# ---------------------------------------------------------------------------
# Confidence line parser
# ---------------------------------------------------------------------------

_CONFIDENCE_RE = re.compile(
    r"^CONFIDENCE:\s*(grounded|partial|needs_review)\s*$",
    re.IGNORECASE,
)


def _parse_confidence_line(content: str) -> str:
    """
    Extract the self-assessed confidence badge from the LAST line of LLM output.

    Rules:
    - The CONFIDENCE: line MUST be the last line (after stripping trailing newlines).
    - If the last line matches `CONFIDENCE: grounded|partial|needs_review`, return
      the matched value (lowercased).
    - If it is missing or malformed, return "needs_review" (safe default).
    """
    stripped = content.rstrip("\n\r ")
    # Attempt to find the last non-empty line
    last_line = stripped.rsplit("\n", 1)[-1].strip()
    match = _CONFIDENCE_RE.match(last_line)
    if match:
        return match.group(1).lower()
    return "needs_review"


def _strip_confidence_line(content: str) -> str:
    """
    Remove the CONFIDENCE: line from the end of the LLM output so it is not
    stored as part of the note body.
    """
    stripped = content.rstrip("\n\r ")
    last_line = stripped.rsplit("\n", 1)[-1].strip()
    if _CONFIDENCE_RE.match(last_line):
        # Remove the last line
        parts = stripped.rsplit("\n", 1)
        if len(parts) == 2:
            return parts[0].rstrip()
        # The entire content was only the CONFIDENCE line
        return ""
    return content


# ---------------------------------------------------------------------------
# LLM call (Gemini API)
# ---------------------------------------------------------------------------


async def _call_gemini(model_name: str, prompt: str) -> str:
    """
    Call the Gemini API and return the generated text.

    Uses google.generativeai synchronously inside an async function (acceptable
    for a single-worker dev server; use asyncio.to_thread for production scale).

    Raises
    ------
    GenerationError
        If the API call fails for any reason.
    """
    try:
        import google.generativeai as genai

        model = genai.GenerativeModel(model_name=model_name)
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:  # noqa: BLE001
        raise GenerationError(
            f"Gemini API call failed: {exc}", reason="llm_failure"
        ) from exc


# ---------------------------------------------------------------------------
# Core generation function
# ---------------------------------------------------------------------------


async def generate_note(
    session: AsyncSession,
    topic_id: uuid.UUID,
    depth: str,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """
    Generate a RAG-grounded study note for *topic_id* at *depth*.

    Flow
    ----
    1. Validate depth (caller should pre-validate, but we guard here too).
    2. Resolve topic from DB — raises ValueError if not found.
    3. Retrieve top-5 chunks via semantic_search scoped to topic_id.
    4. Gate: if max(cosine_similarity) < 0.5 → raise CoverageInsufficient.
    5. Build depth-tiered prompt (C2).
    6. Call Gemini API (gemini-1.5-pro for 10mark, gemini-1.5-flash for others).
    7. Parse CONFIDENCE line from last line of LLM output.
    8. Strip CONFIDENCE line from note body.
    9. Call Confidence Validator stub — may update badge.
    10. Check hash / version (via diff utilities) unless force_regenerate.
    11. Store Note record.
    12. Return { note_id, confidence, content_md }.

    Parameters
    ----------
    session:
        Active async database session.
    topic_id:
        UUID of the topic to generate notes for.
    depth:
        One of "2mark", "6mark", "10mark".
    force_regenerate:
        When True, bypass hash check and regenerate unconditionally.

    Returns
    -------
    dict with keys: note_id (str), confidence (str), content_md (str).

    Raises
    ------
    ValueError
        If topic_id does not resolve to an existing topic.
    CoverageInsufficient
        If max(cosine_similarity) < 0.5 across top-5 chunks.
    GenerationError
        If the LLM call fails.
    """
    from app.services.generation.diff import (
        apply_version_bump,
        check_hash_changed,
        compute_topic_hash,
    )

    if depth not in VALID_DEPTHS:
        raise ValueError(f"Invalid depth '{depth}'. Must be one of {VALID_DEPTHS}.")

    # Step 2: Resolve topic
    topic: Optional[Topic] = await get_topic_by_id(session, topic_id)
    if topic is None:
        raise ValueError(f"Topic '{topic_id}' not found.")

    # Step 3: Retrieve top-5 chunks scoped to topic_id
    chunks = await semantic_search(
        session,
        query_text=topic.name,
        topic_id=topic_id,
        k=5,
    )

    # Step 4: Similarity gate
    if not chunks:
        raise CoverageInsufficient(
            "No chunks available for this topic — not covered in provided material."
        )
    max_similarity = max(c["cosine_similarity"] for c in chunks)
    if max_similarity < SIMILARITY_THRESHOLD:
        raise CoverageInsufficient(
            f"Max cosine similarity {max_similarity:.4f} < {SIMILARITY_THRESHOLD} — "
            "not covered in provided material."
        )

    # Step 5: Build prompt
    prompt = _build_prompt(topic.name, depth, chunks)

    # Step 6: Call LLM (raises GenerationError on failure — NO note is written)
    model_name = _GEMINI_MODEL[depth]
    raw_output = await _call_gemini(model_name, prompt)

    # Step 7: Parse confidence badge from last line
    self_assessed_badge = _parse_confidence_line(raw_output)

    # Step 8: Strip confidence line from note body
    content_md = _strip_confidence_line(raw_output)

    # Step 9: Call Confidence Validator stub
    #          (Task 8 will replace with real second-pass LLM validator)
    new_note_placeholder_id = uuid.uuid4()
    final_badge = await validate_note(
        session,
        new_note_placeholder_id,
        raw_output,  # pass full output including CONFIDENCE line for stub
        chunks,
    )

    # Step 10: Hash / version check (only when not force_regenerate)
    new_hash = compute_topic_hash(topic.name)
    should_bump_version = force_regenerate or check_hash_changed(topic, new_hash)

    # Step 11: Store Note record
    # Check for existing note at this depth to determine version
    existing_note_result = await session.execute(
        select(Note)
        .where(Note.topic_id == topic_id, Note.depth == depth)
        .order_by(Note.version.desc())
        .limit(1)
    )
    existing_note: Optional[Note] = existing_note_result.scalars().first()

    if existing_note is not None and should_bump_version:
        # Bump version — write note_versions history record
        new_version = existing_note.version + 1
        # Update the existing note in-place (notes table = current version)
        existing_note.version = new_version
        existing_note.content_md = content_md
        existing_note.confidence = final_badge
        existing_note.generated_at = datetime.now(timezone.utc)
        note = existing_note
        await apply_version_bump(session, topic, new_hash, note)
    elif existing_note is not None and not should_bump_version:
        # Content unchanged — return existing note (no write)
        return {
            "note_id": str(existing_note.id),
            "confidence": existing_note.confidence,
            "content_md": existing_note.content_md,
        }
    else:
        # First generation for this topic+depth
        note = Note(
            topic_id=topic_id,
            version=1,
            depth=depth,
            content_md=content_md,
            confidence=final_badge,
            generated_at=datetime.now(timezone.utc),
        )
        session.add(note)
        await session.flush()
        await session.refresh(note)
        # Update topic hash on first generation
        topic.content_hash = new_hash

    return {
        "note_id": str(note.id),
        "confidence": final_badge,
        "content_md": content_md,
    }


# ---------------------------------------------------------------------------
# GET /notes/{topic_id} helper
# ---------------------------------------------------------------------------


async def get_notes_for_topic(
    session: AsyncSession,
    topic_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """
    Return all notes for *topic_id* ordered by depth, then version descending.

    Returns
    -------
    list[dict]
        Each dict: note_id, topic_id, depth, version, confidence, content_md, generated_at.
    """
    result = await session.execute(
        select(Note)
        .where(Note.topic_id == topic_id)
        .order_by(Note.depth, Note.version.desc())
    )
    notes = result.scalars().all()
    return [
        {
            "note_id": str(n.id),
            "topic_id": str(n.topic_id),
            "depth": n.depth,
            "version": n.version,
            "confidence": n.confidence,
            "content_md": n.content_md,
            "generated_at": n.generated_at.isoformat(),
        }
        for n in notes
    ]
