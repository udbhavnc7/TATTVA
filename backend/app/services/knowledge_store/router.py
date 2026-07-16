"""
Knowledge Store router.

Endpoints (mounted at root — no prefix):
    POST   /subjects                  — Create a subject
    GET    /subjects                  — List subjects
    POST   /subjects/{id}/modules     — Create a module
    GET    /subjects/{id}/modules     — List modules for a subject
    GET    /topics/{topic_id}         — Get topic details
    GET    /search                    — Semantic chunk search (?q=&k=&topic_id=)
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.services.knowledge_store import service

router = APIRouter(prefix="", tags=["knowledge_store"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SubjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    code: str = Field(..., min_length=4, max_length=10)


class SubjectResponse(BaseModel):
    id: str
    name: str
    code: str
    created_at: str

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "SubjectResponse":
        return cls(
            id=str(obj.id),
            name=obj.name,
            code=obj.code,
            created_at=obj.created_at.isoformat(),
        )


class ModuleCreate(BaseModel):
    number: int
    title: str = Field(..., min_length=1, max_length=255)


class ModuleResponse(BaseModel):
    id: str
    subject_id: str
    number: int
    title: str

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "ModuleResponse":
        return cls(
            id=str(obj.id),
            subject_id=str(obj.subject_id),
            number=obj.number,
            title=obj.title,
        )


class TopicResponse(BaseModel):
    id: str
    module_id: str
    name: str
    version: int
    pending_review: bool
    last_updated: str

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "TopicResponse":
        return cls(
            id=str(obj.id),
            module_id=str(obj.module_id),
            name=obj.name,
            version=obj.version,
            pending_review=obj.pending_review,
            last_updated=obj.last_updated.isoformat(),
        )


class SearchResultItem(BaseModel):
    chunk_id: str
    text: str
    cosine_similarity: float
    source_filename: str
    page_number: int
    subject_id: Optional[str]
    module_id: Optional[str]
    topic_id: Optional[str]


class SearchResponse(BaseModel):
    results: list[SearchResultItem]


# ---------------------------------------------------------------------------
# Subject endpoints
# ---------------------------------------------------------------------------


@router.post("/subjects", status_code=201)
async def create_subject(body: SubjectCreate) -> SubjectResponse:
    """
    POST /subjects — create a new subject.

    Returns 409 if a subject with the same code already exists.
    Returns 400 if the code format is invalid (4–10 alphanumeric characters).
    """
    async with get_db() as session:
        # Validate code format
        if not service.validate_subject_code(body.code):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_subject_code",
                    "detail": "Subject code must be 4–10 alphanumeric characters.",
                },
            )

        # Check uniqueness
        existing = await service.get_subject_by_code(session, body.code)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_subject_code",
                    "existing_subject_id": str(existing.id),
                    "code": body.code,
                },
            )

        subject = await service.create_subject(session, body.name, body.code)
        return SubjectResponse.from_orm_obj(subject)


@router.get("/subjects")
async def list_subjects() -> list[SubjectResponse]:
    """GET /subjects — return all subjects."""
    async with get_db() as session:
        subjects = await service.get_all_subjects(session)
        return [SubjectResponse.from_orm_obj(s) for s in subjects]


# ---------------------------------------------------------------------------
# Module endpoints
# ---------------------------------------------------------------------------


@router.post("/subjects/{subject_id}/modules", status_code=201)
async def create_module(
    subject_id: uuid.UUID,
    body: ModuleCreate,
) -> ModuleResponse:
    """
    POST /subjects/{id}/modules — create a module for a subject.

    Returns 404 if the subject does not exist.
    Returns 409 if a module with the same number already exists for that subject.
    """
    async with get_db() as session:
        subject = await service.get_subject_by_id(session, subject_id)
        if subject is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "subject_not_found", "subject_id": str(subject_id)},
            )

        existing_module = await service.get_module_by_subject_and_number(
            session, subject_id, body.number
        )
        if existing_module is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_module_number",
                    "subject_id": str(subject_id),
                    "number": body.number,
                },
            )

        module = await service.create_module(
            session, subject_id, body.number, body.title
        )
        return ModuleResponse.from_orm_obj(module)


@router.get("/subjects/{subject_id}/modules")
async def list_modules(subject_id: uuid.UUID) -> list[ModuleResponse]:
    """
    GET /subjects/{id}/modules — list all modules for a subject.

    Returns 404 if the subject does not exist.
    """
    async with get_db() as session:
        subject = await service.get_subject_by_id(session, subject_id)
        if subject is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "subject_not_found", "subject_id": str(subject_id)},
            )

        modules = await service.get_modules_for_subject(session, subject_id)
        return [ModuleResponse.from_orm_obj(m) for m in modules]


# ---------------------------------------------------------------------------
# Topic endpoint
# ---------------------------------------------------------------------------


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: uuid.UUID) -> TopicResponse:
    """
    GET /topics/{topic_id} — retrieve topic details.

    Returns 404 if the topic does not exist.
    """
    async with get_db() as session:
        topic = await service.get_topic_by_id(session, topic_id)
        if topic is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "topic_not_found", "topic_id": str(topic_id)},
            )
        return TopicResponse.from_orm_obj(topic)


# ---------------------------------------------------------------------------
# Semantic search endpoint
# ---------------------------------------------------------------------------


@router.get("/search")
async def search_chunks(
    q: str = Query(..., description="Search query text"),
    topic_id: Optional[uuid.UUID] = Query(None, description="Filter by topic UUID"),
    k: int = Query(5, ge=1, description="Number of results to return (default 5)"),
) -> SearchResponse:
    """
    GET /search?q=<text>&topic_id=<UUID>&k=<integer>

    Generates a query embedding, runs pgvector cosine-similarity search,
    and returns top-k results sorted descending by similarity.

    Returns 500 on any search failure.
    """
    try:
        async with get_db() as session:
            results = await service.semantic_search(session, q, topic_id, k)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"error": "search_failed", "detail": str(exc)},
        ) from exc

    return SearchResponse(
        results=[SearchResultItem(**item) for item in results]
    )


# ---------------------------------------------------------------------------
# Health check (kept for convenience)
# ---------------------------------------------------------------------------


@router.get("/knowledge/health")
async def health() -> dict:
    """Health-check for the Knowledge Store Service."""
    return {"service": "knowledge_store", "status": "ok"}
