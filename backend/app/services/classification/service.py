"""
Classification Service — business logic layer.

Handles:
  - LLM-powered taxonomy classification (C1 prompt, gemini-1.5-flash)
  - Single-retry logic on LLM error or JSON parse failure
  - Atomic taxonomy creation (subject → module → topic in FK order)
  - Low-confidence handling (pending_review flag + ≤200-char note)
  - Writing the classification record

Public API
----------
  classify_document(document_id, headings, content, session) -> ClassificationResult | None
  validate_classification_output(output: dict) -> bool
  create_taxonomy_if_needed(session, result) -> tuple[Subject, Module, Topic]
  write_classification_record(session, document_id, result, pending_review) -> Classification
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Classification, Document, Module, Subject, Topic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema type alias / dataclass
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """Validated LLM classification output."""
    subject: str
    module_number: int
    topic: str
    is_new_topic: bool
    confidence: str          # "high" | "medium" | "low"
    note: Optional[str]      # max 200 chars; required when confidence == "low"


# ---------------------------------------------------------------------------
# C1 Prompt template
# ---------------------------------------------------------------------------

_C1_PROMPT_TEMPLATE = """\
You are Tattva's content classifier. Given document headings and content, map the \
material to the most appropriate exam taxonomy entry.

DOCUMENT HEADINGS:
{headings}

DOCUMENT CONTENT (first 3000 chars):
{content}

Output ONLY a single valid JSON object (no markdown, no explanation) conforming \
exactly to this schema:
{{
  "subject": "<string — name of the academic subject, e.g. 'Operating Systems'>",
  "module_number": <integer — module/chapter number, e.g. 3>,
  "topic": "<string — specific topic name within that module>",
  "is_new_topic": <boolean — true if this is a new topic not yet in the taxonomy>,
  "confidence": "<'high' | 'medium' | 'low'>",
  "note": "<string, optional — include ONLY when confidence is 'low', max 200 chars, \
explaining the uncertainty>"
}}

Rules:
- confidence == 'high'   → exact match to known subject/module/topic
- confidence == 'medium' → partial match; proposing a new module or topic
- confidence == 'low'    → uncertain; note field is REQUIRED and must be ≤ 200 chars
- Do NOT include the 'note' field when confidence is 'high' or 'medium'.
- Output ONLY the JSON object.
"""


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def validate_classification_output(output: dict) -> bool:
    """
    Return True iff *output* contains all required fields with correct types.

    Required fields:
      subject       : str (non-empty)
      module_number : int
      topic         : str (non-empty)
      is_new_topic  : bool
      confidence    : "high" | "medium" | "low"
      note          : str | None (optional; max 200 chars when present)
    """
    if not isinstance(output, dict):
        return False

    # Required fields presence & types
    if not isinstance(output.get("subject"), str) or not output["subject"].strip():
        return False
    if not isinstance(output.get("module_number"), int):
        return False
    if not isinstance(output.get("topic"), str) or not output["topic"].strip():
        return False
    if not isinstance(output.get("is_new_topic"), bool):
        return False

    confidence = output.get("confidence")
    if confidence not in ("high", "medium", "low"):
        return False

    note = output.get("note")
    if note is not None:
        if not isinstance(note, str):
            return False
        if len(note) > 200:
            return False

    # When confidence is 'low' note is required
    if confidence == "low":
        if note is None or not note.strip():
            return False

    return True


def _build_classification_result(output: dict) -> ClassificationResult:
    """Convert a validated dict to ClassificationResult."""
    note_raw: Optional[str] = output.get("note")
    # Truncate just in case (should already be validated at this point)
    if note_raw is not None:
        note_raw = note_raw[:200]
    return ClassificationResult(
        subject=output["subject"].strip(),
        module_number=int(output["module_number"]),
        topic=output["topic"].strip(),
        is_new_topic=bool(output["is_new_topic"]),
        confidence=output["confidence"],
        note=note_raw if note_raw else None,
    )


def _extract_json_from_response(text: str) -> dict:
    """
    Extract and parse a JSON object from the LLM response text.

    Strips markdown fences if present, then parses JSON.
    Raises ValueError on parse failure.
    """
    # Strip markdown code fences
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON parse error: {exc}") from exc


# ---------------------------------------------------------------------------
# LLM call (wraps google.generativeai)
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> str:
    """
    Call gemini-1.5-flash with *prompt* and return the text response.

    Raises RuntimeError on any API error.
    Imported lazily so tests can mock `google.generativeai` before import.
    """
    try:
        import google.generativeai as genai  # type: ignore
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        raise RuntimeError(f"LLM call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Core classification function (4.1 + 4.2)
# ---------------------------------------------------------------------------

async def classify_document(
    document_id: uuid.UUID,
    headings: list[str],
    content: str,
    session: AsyncSession,
) -> Optional[ClassificationResult]:
    """
    Classify a document using the C1 LLM prompt.

    Attempts up to 2 calls (original + 1 retry). On both failures, marks
    the document as 'classification_failed' and returns None.

    Parameters
    ----------
    document_id : UUID of the document being classified
    headings    : list of heading strings extracted by the parser
    content     : document body text (first chunk is sufficient)
    session     : active AsyncSession for DB operations

    Returns
    -------
    ClassificationResult on success, None on failure.
    """
    headings_text = "\n".join(f"- {h}" for h in headings) if headings else "(none)"
    content_snippet = content[:3000]
    prompt = _C1_PROMPT_TEMPLATE.format(
        headings=headings_text,
        content=content_snippet,
    )

    last_error: Optional[Exception] = None
    for attempt in range(2):  # attempt 0 = original, attempt 1 = retry
        try:
            raw_text = _call_llm(prompt)
            output = _extract_json_from_response(raw_text)
            if not validate_classification_output(output):
                raise ValueError(
                    f"LLM output failed schema validation: {output!r}"
                )
            result = _build_classification_result(output)
            logger.info(
                "Document %s classified: subject=%r confidence=%r (attempt %d)",
                document_id,
                result.subject,
                result.confidence,
                attempt,
            )
            return result
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Classification attempt %d failed for document %s: %s",
                attempt,
                document_id,
                exc,
            )

    # Both attempts failed — mark document as classification_failed
    logger.error(
        "Both classification attempts failed for document %s. Marking as classification_failed.",
        document_id,
    )
    await _mark_document_failed(session, document_id)
    return None


async def _mark_document_failed(
    session: AsyncSession, document_id: uuid.UUID
) -> None:
    """Set document.status = 'classification_failed'."""
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    doc: Optional[Document] = result.scalars().first()
    if doc is not None:
        doc.status = "classification_failed"
        session.add(doc)
        await session.flush()


# ---------------------------------------------------------------------------
# Atomic taxonomy creation (4.3)
# ---------------------------------------------------------------------------

async def create_taxonomy_if_needed(
    session: AsyncSession,
    result: ClassificationResult,
) -> tuple[Subject, Module, Topic]:
    """
    Atomically create Subject → Module → Topic records if they do not yet exist.

    Creation order respects FK constraints:
      1. Subject  (subjects table)
      2. Module   (modules table, FK → subjects)
      3. Topic    (topics table, FK → modules)

    Returns a (subject, module, topic) tuple for all three records
    (whether newly created or pre-existing).

    This function must be called inside an active transaction; the caller
    (router or classify_document flow) is responsible for commit.
    """
    # --- 1. Subject ---
    subject_result = await session.execute(
        select(Subject).where(Subject.name == result.subject)
    )
    subject: Optional[Subject] = subject_result.scalars().first()

    if subject is None:
        # Derive a code from the subject name (first 4–10 alphanumeric chars,
        # upper-cased). The code uniqueness constraint is enforced by the DB.
        raw_code = re.sub(r"[^A-Za-z0-9]", "", result.subject).upper()
        code = (raw_code[:10] if len(raw_code) >= 4 else (raw_code + "SUBJ")[:10])
        if len(code) < 4:
            code = (code + "SUBJ")[:10]
        subject = Subject(name=result.subject, code=code)
        session.add(subject)
        await session.flush()  # populates subject.id
        logger.info("Created new Subject: %r (code=%r)", result.subject, code)

    # --- 2. Module ---
    module_result = await session.execute(
        select(Module).where(
            Module.subject_id == subject.id,
            Module.number == result.module_number,
        )
    )
    module: Optional[Module] = module_result.scalars().first()

    if module is None:
        module = Module(
            subject_id=subject.id,
            number=result.module_number,
            title=f"Module {result.module_number}",
        )
        session.add(module)
        await session.flush()  # populates module.id
        logger.info(
            "Created new Module: number=%d under subject %s",
            result.module_number,
            subject.id,
        )

    # --- 3. Topic ---
    topic_result = await session.execute(
        select(Topic).where(
            Topic.module_id == module.id,
            Topic.name == result.topic,
        )
    )
    topic: Optional[Topic] = topic_result.scalars().first()

    if topic is None:
        topic = Topic(
            module_id=module.id,
            name=result.topic,
        )
        session.add(topic)
        await session.flush()  # populates topic.id
        logger.info(
            "Created new Topic: %r under module %s",
            result.topic,
            module.id,
        )

    return subject, module, topic


# ---------------------------------------------------------------------------
# Classification record writer (4.4)
# ---------------------------------------------------------------------------

async def write_classification_record(
    session: AsyncSession,
    document_id: uuid.UUID,
    result: ClassificationResult,
    pending_review: bool,
) -> Classification:
    """
    Persist a Classification record to the database.

    When confidence == 'low', pending_review must be True and note must be
    non-empty and ≤ 200 chars (validated by validate_classification_output
    before this call).

    Returns the persisted Classification instance.
    """
    classification = Classification(
        document_id=document_id,
        subject=result.subject,
        module_number=result.module_number,
        topic=result.topic,
        is_new_topic=result.is_new_topic,
        confidence=result.confidence,
        note=result.note,
        pending_review=pending_review,
    )
    session.add(classification)
    await session.flush()
    await session.refresh(classification)
    logger.info(
        "Wrote classification record %s for document %s (confidence=%r, pending_review=%s)",
        classification.id,
        document_id,
        result.confidence,
        pending_review,
    )
    return classification
