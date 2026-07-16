"""
Confidence Validator — Task 8.

Public API
----------
validate_note(session, note_id, note_content, cited_chunks) -> str
    Second-pass hallucination detection using prompt C8.

    Calls Gemini Flash with a 30-second timeout to check each sentence of the
    note against the cited source chunks. Any sentence the LLM identifies as
    NOT supported by the chunks is flagged as unsupported.

    Behaviour
    ---------
    * Unsupported sentences found  → creates ValidationFlag rows in the DB,
                                     returns "needs_review"
    * All sentences supported      → returns the original self-assessed badge
                                     (parsed from note_content via
                                     _parse_confidence_line)
    * Any exception (LLM error,
      timeout, JSON parse error)   → logs a warning, returns the original badge
                                     unchanged; does NOT abort note storage
    * note_content is NEVER modified by this function (read-only on content_md)

Design notes
------------
- Uses Gemini Flash (fast/cheap) for the second-pass check.
- Prompt C8 asks the model to return ONLY a JSON array of unsupported sentences.
- asyncio.wait_for enforces the 30-second timeout on the LLM call.
- ValidationFlag rows are stored in validation_flags table; never embedded in the
  note body.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ValidationFlag

# Duplicate the confidence-line parser here to avoid a circular import
# with service.py (which imports validate_note from this module).
import re as _re
_CONFIDENCE_PARSE_RE = _re.compile(
    r"^CONFIDENCE:\s*(grounded|partial|needs_review)\s*$",
    _re.IGNORECASE,
)


def _parse_confidence_line(content: str) -> str:
    """Extract self-assessed badge from last line; default 'needs_review'."""
    stripped = content.rstrip("\n\r ")
    last_line = stripped.rsplit("\n", 1)[-1].strip()
    match = _CONFIDENCE_PARSE_RE.match(last_line)
    if match:
        return match.group(1).lower()
    return "needs_review"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt C8 template
# ---------------------------------------------------------------------------

_PROMPT_C8_TEMPLATE = (
    "Review this study note against the cited source chunks. "
    "List any sentences that are NOT supported by the provided chunks. "
    "Return ONLY a JSON array of unsupported sentences, "
    'e.g. ["sentence 1", "sentence 2"] or [] if all are supported.\n\n'
    "Note:\n{note}\n\nCited chunks:\n{chunks}\n"
)

# Timeout for the LLM call (seconds)
_VALIDATOR_TIMEOUT = 30.0

# Gemini Flash model for the second-pass (cheaper/faster)
_VALIDATOR_MODEL = "gemini-1.5-flash"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_c8_prompt(note_content: str, cited_chunks: list[dict]) -> str:
    """Assemble the C8 prompt from note content and cited chunk texts."""
    chunk_parts: list[str] = []
    for idx, chunk in enumerate(cited_chunks, start=1):
        filename = chunk.get("source_filename", "unknown.pdf")
        page = chunk.get("page_number", 0)
        text = chunk.get("text", "")
        chunk_parts.append(f"[Chunk {idx} — Source: {filename}, p.{page}]\n{text}")

    chunks_block = "\n\n---\n\n".join(chunk_parts) if chunk_parts else "(no chunks provided)"

    return _PROMPT_C8_TEMPLATE.format(note=note_content, chunks=chunks_block)


async def _call_gemini_flash(prompt: str) -> str:
    """
    Call Gemini Flash and return the raw response text.

    Wrapped in asyncio.wait_for to enforce the 30-second timeout.

    Raises
    ------
    asyncio.TimeoutError
        If the call does not complete within _VALIDATOR_TIMEOUT seconds.
    Exception
        Any Gemini API error propagates up to the caller (validate_note).
    """
    import google.generativeai as genai  # type: ignore[import]

    model = genai.GenerativeModel(model_name=_VALIDATOR_MODEL)

    async def _invoke() -> str:
        # google.generativeai is synchronous; run in thread pool for prod safety
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, model.generate_content, prompt)
        return response.text

    return await asyncio.wait_for(_invoke(), timeout=_VALIDATOR_TIMEOUT)


def _parse_unsupported_sentences(raw_response: str) -> list[str]:
    """
    Parse the LLM response into a list of unsupported sentences.

    The LLM is asked to return a JSON array.  If the response is not valid
    JSON, or is not a list, we conservatively return an empty list (treat all
    as supported) rather than crashing — the outer exception handler in
    validate_note will log and preserve the badge anyway.

    Returns
    -------
    list[str]
        Unsupported sentence strings, or [] if none / parse failure.
    """
    text = raw_response.strip()
    # Strip markdown code fences if the model wrapped the JSON
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        inner = [
            line for line in lines
            if not line.strip().startswith("```")
        ]
        text = "\n".join(inner).strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Validator: failed to parse LLM JSON response — treating as all-supported")
        return []
    if isinstance(parsed, list):
        return [str(s) for s in parsed if str(s).strip()]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def validate_note(
    session: AsyncSession,
    note_id: uuid.UUID,
    note_content: str,
    cited_chunks: list[dict],
) -> str:
    """
    Confidence Validator — second-pass hallucination detection (Task 8).

    Calls Gemini Flash (prompt C8) to identify sentences in *note_content*
    that are NOT supported by *cited_chunks*.  Flags found sentences are
    persisted to the ``validation_flags`` table.

    Parameters
    ----------
    session:
        Active async database session.
    note_id:
        UUID of the note being validated.
    note_content:
        Full Markdown content of the generated note (including the CONFIDENCE
        line if still present).  This string is NEVER modified.
    cited_chunks:
        Top-k retrieved chunks used to generate the note.

    Returns
    -------
    str
        * ``"needs_review"`` if any unsupported sentences were found.
        * The original self-assessed badge (extracted from *note_content*)
          if all sentences are supported.
        * The original self-assessed badge (unchanged) on any failure.

    Notes
    -----
    * This function is read-only with respect to *note_content*.
    * On validator failure the existing badge is preserved and the failure
      is logged — note storage is never aborted.
    """
    # Determine the original badge from the note content (safe default = needs_review)
    original_badge: str = _parse_confidence_line(note_content)

    try:
        # --- Step 1: Build the C8 prompt ---
        prompt = _build_c8_prompt(note_content, cited_chunks)

        # --- Step 2: Call Gemini Flash with 30-second timeout ---
        raw_response = await _call_gemini_flash(prompt)

        # --- Step 3: Parse the response ---
        unsupported: list[str] = _parse_unsupported_sentences(raw_response)

        # --- Step 4: Persist flags if any unsupported sentences found ---
        if unsupported:
            now = datetime.now(timezone.utc)
            for sentence in unsupported:
                flag = ValidationFlag(
                    note_id=note_id,
                    flagged_sentence=sentence,
                    flagged_at=now,
                )
                session.add(flag)
            await session.flush()
            # Badge downgrade — unconditional when any unsupported sentence found
            return "needs_review"

        # --- Step 5: All supported — return original badge unchanged ---
        return original_badge

    except Exception as exc:  # noqa: BLE001
        # Validator failure must NOT abort note storage.
        # Log the failure and return the original badge unchanged.
        logger.warning(
            "Confidence Validator failed for note_id=%s: %s",
            note_id,
            exc,
        )
        return original_badge
