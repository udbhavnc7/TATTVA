"""
Generation Service router — Task 7.

Endpoints mounted at root (no /generate prefix):
    POST /generate-notes              — Generate a grounded note (topic_id + depth)
    GET  /notes/{topic_id}            — Get all notes for a topic
    POST /topics/{id}/regenerate      — Force-regenerate (bypasses hash check)
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db.session import get_db
from app.services.generation import service as gen_service
from app.services.generation.service import (
    CoverageInsufficient,
    GenerationError,
    VALID_DEPTHS,
)
from app.services.knowledge_store.service import get_topic_by_id

# Mount at root so endpoints sit at /generate-notes, /notes/..., /topics/.../regenerate
router = APIRouter(prefix="", tags=["generation"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class GenerateNotesRequest(BaseModel):
    topic_id: uuid.UUID
    depth: str = Field(..., description="One of: 2mark, 6mark, 10mark")
    force_regenerate: bool = Field(
        default=False,
        description="When true, bypasses hash comparison and re-generates unconditionally",
    )

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: str) -> str:
        if v not in VALID_DEPTHS:
            raise ValueError(f"depth must be one of {sorted(VALID_DEPTHS)}")
        return v


class GenerateNotesResponse(BaseModel):
    note_id: str
    confidence: str
    content_md: str


class NoteListItem(BaseModel):
    note_id: str
    topic_id: str
    depth: str
    version: int
    confidence: str
    content_md: str
    generated_at: str


class RegenerateRequest(BaseModel):
    depth: str = Field(..., description="One of: 2mark, 6mark, 10mark")

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: str) -> str:
        if v not in VALID_DEPTHS:
            raise ValueError(f"depth must be one of {sorted(VALID_DEPTHS)}")
        return v


# ---------------------------------------------------------------------------
# POST /generate-notes  (Task 7.1 – 7.5)
# ---------------------------------------------------------------------------


@router.post("/generate-notes", response_model=GenerateNotesResponse)
async def generate_notes(body: GenerateNotesRequest) -> GenerateNotesResponse:
    """
    POST /generate-notes

    Validate topic_id (UUID, must resolve to existing topic) and depth
    (2mark | 6mark | 10mark); return 400 for invalid inputs.

    Retrieves top-5 chunks via semantic search for topic_id.
    Returns 422 if max(cosine_similarity) < 0.5 — "Not covered in provided material".
    Calls Gemini API (gemini-1.5-pro for 10mark, gemini-1.5-flash for 2mark/6mark).
    Parses CONFIDENCE: line and stores note only after Confidence Validator completes.
    Returns { note_id, confidence, content_md } on success.
    Returns 500 on LLM failure — no note is written.
    """
    # Depth validation is handled by the Pydantic validator above (raises 422 on invalid).
    # We re-map that to a 400 via exception handler below.
    async with get_db() as session:
        # Validate topic_id resolves
        topic = await get_topic_by_id(session, body.topic_id)
        if topic is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_topic_id",
                    "detail": f"Topic '{body.topic_id}' not found.",
                },
            )

        try:
            result = await gen_service.generate_note(
                session=session,
                topic_id=body.topic_id,
                depth=body.depth,
                force_regenerate=body.force_regenerate,
            )
        except CoverageInsufficient:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "coverage_insufficient",
                    "detail": "Not covered in provided material",
                },
            )
        except GenerationError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "generation_failed",
                    "topic_id": str(body.topic_id),
                    "reason": exc.reason,
                    "detail": str(exc),
                },
            )
        except ValueError as exc:
            # Should not normally reach here (topic validation above), but guard
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            )

    return GenerateNotesResponse(**result)


# ---------------------------------------------------------------------------
# GET /notes/{topic_id}  (Task 7.6)
# ---------------------------------------------------------------------------


@router.get("/notes/{topic_id}", response_model=List[NoteListItem])
async def get_notes(topic_id: uuid.UUID) -> List[NoteListItem]:
    """
    GET /notes/{topic_id}

    Returns all notes for a topic ordered by depth, then version descending.
    Returns 404 if the topic does not exist.
    Returns an empty list if the topic exists but has no notes.
    """
    async with get_db() as session:
        # Confirm topic exists
        topic = await get_topic_by_id(session, topic_id)
        if topic is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "topic_not_found",
                    "topic_id": str(topic_id),
                },
            )

        notes = await gen_service.get_notes_for_topic(session, topic_id)

    return [NoteListItem(**n) for n in notes]


# ---------------------------------------------------------------------------
# POST /topics/{id}/regenerate  (Task 7.6)
# ---------------------------------------------------------------------------


@router.post("/topics/{topic_id}/regenerate", response_model=GenerateNotesResponse)
async def regenerate_notes(
    topic_id: uuid.UUID,
    body: RegenerateRequest,
) -> GenerateNotesResponse:
    """
    POST /topics/{id}/regenerate

    Force-regenerate note for topic_id at the given depth.
    Bypasses hash check (force_regenerate=True) and re-runs the full pipeline.

    Returns 400 if topic_id is invalid or depth is not recognized.
    Returns 422 if max similarity < 0.5.
    Returns 500 on LLM failure.
    """
    async with get_db() as session:
        topic = await get_topic_by_id(session, topic_id)
        if topic is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_topic_id",
                    "detail": f"Topic '{topic_id}' not found.",
                },
            )

        try:
            result = await gen_service.generate_note(
                session=session,
                topic_id=topic_id,
                depth=body.depth,
                force_regenerate=True,
            )
        except CoverageInsufficient:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "coverage_insufficient",
                    "detail": "Not covered in provided material",
                },
            )
        except GenerationError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "generation_failed",
                    "topic_id": str(topic_id),
                    "reason": exc.reason,
                    "detail": str(exc),
                },
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            )

    return GenerateNotesResponse(**result)


# ---------------------------------------------------------------------------
# Health check (retained for smoke tests)
# ---------------------------------------------------------------------------


@router.get("/generate/health")
async def health() -> dict:
    """Health-check for the Generation Service."""
    return {"service": "generation", "status": "ok"}
