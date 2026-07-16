"""
Classification Service router.

Endpoints:
    POST /classify/{document_id} — Trigger LLM taxonomy classification for a parsed document
    GET  /classify/health        — Service health check
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.session import get_db
from app.services.classification.service import (
    ClassificationResult,
    classify_document,
    create_taxonomy_if_needed,
    write_classification_record,
)

router = APIRouter(prefix="/classify", tags=["classification"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ClassifyRequest(BaseModel):
    """Body for POST /classify/{document_id}."""

    headings: list[str]
    content: str


class ClassifyResponse(BaseModel):
    """Successful classification response."""

    document_id: uuid.UUID
    subject: str
    module_number: int
    topic: str
    is_new_topic: bool
    confidence: str
    note: Optional[str]
    pending_review: bool
    classification_id: uuid.UUID


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict:
    """Health-check for the Classification Service."""
    return {"service": "classification", "status": "ok"}


@router.post(
    "/{document_id}",
    status_code=200,
    response_model=ClassifyResponse,
    responses={
        200: {"description": "Classification successful"},
        422: {"description": "Classification failed after retries"},
        500: {"description": "Internal server error"},
    },
)
async def trigger_classification(
    document_id: uuid.UUID,
    body: ClassifyRequest,
) -> JSONResponse:
    """
    Run LLM taxonomy classification for a parsed document.

    Steps:
      1. Call the C1 LLM prompt with headings + content (with one retry).
      2. If both attempts fail, document.status is set to 'classification_failed'
         and a 422 is returned.
      3. On success, atomically create Subject/Module/Topic records as needed.
      4. Write the classification record (with pending_review=True for low confidence).
      5. Return the classification details.
    """
    async with get_db() as session:
        # Step 1 + 2: Classify (handles retry internally)
        result: Optional[ClassificationResult] = await classify_document(
            document_id=document_id,
            headings=body.headings,
            content=body.content,
            session=session,
        )

        if result is None:
            # classify_document already set document.status = 'classification_failed'
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "classification_failed",
                    "document_id": str(document_id),
                    "message": "Classification failed after 2 attempts. Document marked as classification_failed.",
                },
            )

        # Step 3: Atomic taxonomy creation (subject → module → topic)
        _subject, _module, _topic = await create_taxonomy_if_needed(session, result)

        # Step 4: Determine pending_review flag
        pending_review = result.confidence == "low"

        # Step 5: Write classification record
        classification = await write_classification_record(
            session=session,
            document_id=document_id,
            result=result,
            pending_review=pending_review,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "document_id": str(document_id),
            "subject": result.subject,
            "module_number": result.module_number,
            "topic": result.topic,
            "is_new_topic": result.is_new_topic,
            "confidence": result.confidence,
            "note": result.note,
            "pending_review": pending_review,
            "classification_id": str(classification.id),
        },
    )
