"""
Knowledge Store router.

Endpoints (mounted at root — no prefix):
    POST   /subjects                  — Create a subject
    GET    /subjects                  — List subjects
    POST   /subjects/{id}/modules     — Create a module
    GET    /subjects/{id}/modules     — List modules for a subject
    GET    /topics/{topic_id}         — Get topic details
    GET    /search                    — Semantic chunk search (?q=&k=&topic_id=)

PYQ Analyzer endpoints (Task 10):
    POST   /pyqs                      — Ingest a PYQ (validates year/marks/question_text)
    GET    /pyqs                      — List PYQs with optional filters
    POST   /pyqs/recalculate          — Deterministic SQL importance recalculation
    GET    /topics/{id}/importance    — Get topic importance score

Formula Scanner endpoints (Task 13):
    GET    /formulas/{subject_id}             — Extract formulas from all chunks for subject
    POST   /formulas/{subject_id}/scan        — Re-run extraction and return completion notification
    GET    /formulas/{subject_id}/export      — Download formula table as .md file
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from fastapi.responses import Response

from app.db.session import get_db
from app.services.knowledge_store import service
from app.services.knowledge_store import pyq_service
from app.services.knowledge_store import formula_service
from app.services.knowledge_store import mock_paper_service

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


# ===========================================================================
# PYQ Analyzer endpoints (Task 10)
# ===========================================================================

# ---------------------------------------------------------------------------
# Pydantic schemas for PYQ
# ---------------------------------------------------------------------------


class PyqCreate(BaseModel):
    subject_id: uuid.UUID
    year: int
    question_text: str
    marks: int
    difficulty: Optional[str] = None
    secondary_topics: Optional[List[uuid.UUID]] = Field(default_factory=list)


class PyqResponse(BaseModel):
    id: str
    subject_id: str
    year: int
    question_text: str
    marks: int
    topic_id: Optional[str]
    is_unmatched: bool
    difficulty: Optional[str]
    difficulty_note: Optional[str]
    secondary_topics: Optional[List[str]]
    created_at: str

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "PyqResponse":
        sec = []
        if obj.secondary_topics:
            sec = [str(t) for t in obj.secondary_topics]
        return cls(
            id=str(obj.id),
            subject_id=str(obj.subject_id),
            year=obj.year,
            question_text=obj.question_text,
            marks=obj.marks,
            topic_id=str(obj.topic_id) if obj.topic_id else None,
            is_unmatched=obj.is_unmatched,
            difficulty=obj.difficulty,
            difficulty_note=obj.difficulty_note,
            secondary_topics=sec,
            created_at=obj.created_at.isoformat(),
        )


class TopicImportanceResponse(BaseModel):
    topic_id: str
    frequency_count: int
    difficulty_avg: Optional[float]
    last_recalculated: Optional[str]


class RecalculateResponse(BaseModel):
    status: str
    rows_affected: int


# ---------------------------------------------------------------------------
# POST /pyqs — ingest a PYQ
# ---------------------------------------------------------------------------


@router.post("/pyqs", status_code=201)
async def create_pyq(body: PyqCreate) -> PyqResponse:
    """
    POST /pyqs — ingest a new Past Year Question.

    Validates:
      - year: 2000 to current calendar year inclusive
      - marks: 1 to 100 inclusive
      - question_text: 10 to 2000 characters inclusive

    On validation failure returns 400 with:
      { "error": "invalid_field", "field": "<fieldname>", "detail": "<reason>" }

    On success runs LLM topic matching (prompt C5) and stores the PYQ.
    Returns 201 with the stored PYQ record.
    """
    # Validate fields
    error = pyq_service.validate_pyq_fields(body.year, body.marks, body.question_text)
    if error is not None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_field",
                "field": error["field"],
                "detail": error["detail"],
            },
        )

    async with get_db() as session:
        # LLM topic matching
        match_result = await pyq_service.match_topic_for_pyq(
            session, body.question_text, body.subject_id
        )

        # Use caller-supplied difficulty if provided; otherwise use LLM result
        difficulty = body.difficulty or match_result["difficulty"]
        if difficulty not in pyq_service.VALID_DIFFICULTIES:
            difficulty = match_result["difficulty"]

        pyq = await pyq_service.create_pyq(
            session=session,
            subject_id=body.subject_id,
            year=body.year,
            question_text=body.question_text,
            marks=body.marks,
            topic_id=match_result["topic_id"],
            is_unmatched=match_result["is_unmatched"],
            difficulty=difficulty,
            difficulty_note=match_result["difficulty_note"],
            secondary_topics=body.secondary_topics,
        )
        return PyqResponse.from_orm_obj(pyq)


# ---------------------------------------------------------------------------
# GET /pyqs — list PYQs with optional filters
# ---------------------------------------------------------------------------


@router.get("/pyqs")
async def list_pyqs(
    subject_id: Optional[uuid.UUID] = Query(None, description="Filter by subject UUID"),
    topic_id: Optional[uuid.UUID] = Query(None, description="Filter by topic UUID"),
    is_unmatched: Optional[bool] = Query(None, description="Filter by unmatched status"),
) -> list[PyqResponse]:
    """
    GET /pyqs — return PYQs with optional filters.

    Query parameters (all optional):
      - subject_id: UUID
      - topic_id: UUID
      - is_unmatched: bool
    """
    async with get_db() as session:
        pyqs = await pyq_service.get_pyqs(
            session,
            subject_id=subject_id,
            topic_id=topic_id,
            is_unmatched=is_unmatched,
        )
        return [PyqResponse.from_orm_obj(p) for p in pyqs]


# ---------------------------------------------------------------------------
# POST /pyqs/recalculate — deterministic SQL importance recalculation
# ---------------------------------------------------------------------------


@router.post("/pyqs/recalculate")
async def recalculate_importance() -> RecalculateResponse:
    """
    POST /pyqs/recalculate — trigger deterministic SQL topic importance recalculation.

    Runs: INSERT INTO topic_importance ... SELECT COUNT(*) GROUP BY topic_id ...
    ON CONFLICT DO UPDATE

    This endpoint NEVER calls an LLM. Frequency counting is purely SQL.
    Must complete in ≤ 10 seconds for 500 PYQ records.
    """
    async with get_db() as session:
        rows = await pyq_service.recalculate_topic_importance(session)
        return RecalculateResponse(status="ok", rows_affected=rows)


# ---------------------------------------------------------------------------
# GET /topics/{id}/importance — get topic importance score
# ---------------------------------------------------------------------------


@router.get("/topics/{topic_id}/importance")
async def get_topic_importance(topic_id: uuid.UUID) -> TopicImportanceResponse:
    """
    GET /topics/{id}/importance — return the topic_importance record.

    If no record exists (topic has no matched PYQs), returns frequency_count = 0.
    """
    async with get_db() as session:
        data = await pyq_service.get_topic_importance(session, topic_id)
        return TopicImportanceResponse(**data)


# ===========================================================================
# Formula Scanner endpoints (Task 13)
# ===========================================================================

# ---------------------------------------------------------------------------
# Pydantic schemas for Formula Scanner
# ---------------------------------------------------------------------------


class FormulaItem(BaseModel):
    formula_or_algorithm: str
    variables: str
    source: str


class FormulaListResponse(BaseModel):
    subject_id: str
    formulas: List[FormulaItem]
    rendered_table: str


class FormulaScanResponse(BaseModel):
    subject_id: str
    formula_count: int
    status: str


# ---------------------------------------------------------------------------
# GET /formulas/{subject_id} — extract and return formulas
# ---------------------------------------------------------------------------


@router.get("/formulas/{subject_id}", response_model=FormulaListResponse)
async def get_formulas(subject_id: uuid.UUID) -> FormulaListResponse:
    """
    GET /formulas/{subject_id}

    Scan all chunks for the subject, extract every formula/equation/algorithm
    pseudocode using regex/heuristic extraction (no LLM).

    Incomplete formulas (containing '...' or cut off mid-expression) are
    flagged with '[incomplete in source]'.

    Returns JSON:
      { subject_id, formulas: [...], rendered_table: str }

    The rendered_table is a Markdown table; falls back to a numbered list if
    table rendering raises an error.
    """
    async with get_db() as session:
        result = await formula_service.scan_formulas(session, subject_id)

    return FormulaListResponse(
        subject_id=result["subject_id"],
        formulas=[FormulaItem(**f) for f in result["formulas"]],
        rendered_table=result["rendered_table"],
    )


# ---------------------------------------------------------------------------
# POST /formulas/{subject_id}/scan — re-run extraction
# ---------------------------------------------------------------------------


@router.post("/formulas/{subject_id}/scan", response_model=FormulaScanResponse)
async def scan_formulas(subject_id: uuid.UUID) -> FormulaScanResponse:
    """
    POST /formulas/{subject_id}/scan

    Re-run formula extraction against the current Knowledge Store state and
    return a completion notification.

    Returns JSON:
      { subject_id, formula_count: int, status: "completed" }
    """
    async with get_db() as session:
        result = await formula_service.scan_formulas(session, subject_id)

    return FormulaScanResponse(
        subject_id=result["subject_id"],
        formula_count=len(result["formulas"]),
        status="completed",
    )


# ---------------------------------------------------------------------------
# GET /formulas/{subject_id}/export — download as .md file
# ---------------------------------------------------------------------------


@router.get("/formulas/{subject_id}/export")
async def export_formulas(subject_id: uuid.UUID) -> Response:
    """
    GET /formulas/{subject_id}/export

    Return the formula table as a downloadable Markdown file.

    Response headers:
      Content-Type: text/markdown
      Content-Disposition: attachment; filename="formulas_<subject_id>.md"
    """
    async with get_db() as session:
        result = await formula_service.scan_formulas(session, subject_id)

    md_content = result["rendered_table"]
    filename = f"formulas_{subject_id}.md"

    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ===========================================================================
# Mock Exam Paper Assembler endpoints (Task 11)
# ===========================================================================

# ---------------------------------------------------------------------------
# Pydantic schemas for Mock Paper
# ---------------------------------------------------------------------------


class MockPaperRequest(BaseModel):
    subject_id: uuid.UUID
    total_marks_target: int = Field(..., gt=0, description="Total marks target (positive integer)")
    question_type_distribution: str = Field(
        ...,
        description="Distribution string, e.g. '2×10mark + 4×6mark + 4×2mark'",
    )


class MockPaperQuestionItem(BaseModel):
    id: str
    year: int
    question_text: str
    marks: int
    topic_tag: str
    topic_id: Optional[str]


class MockPaperResponse(BaseModel):
    questions: List[MockPaperQuestionItem]
    total_marks: int
    warnings: List[str]


# ---------------------------------------------------------------------------
# POST /mock-paper — assemble a mock exam paper
# ---------------------------------------------------------------------------


@router.post("/mock-paper", response_model=MockPaperResponse)
async def create_mock_paper(body: MockPaperRequest) -> MockPaperResponse:
    """
    POST /mock-paper — assemble a mock exam paper.

    Accepts:
      - subject_id: UUID
      - total_marks_target: positive integer
      - question_type_distribution: e.g. "2×10mark + 4×6mark + 4×2mark"

    Selection logic:
      - Rank by topic_importance (frequency_count) descending.
      - Ties broken by most recent year.
      - If all scores are 0, select uniformly at random.

    Stops when total_marks_target is reached (even if distribution not satisfied).

    If the PYQ bank cannot satisfy the distribution, includes a warning per
    unsatisfied type. Does NOT abort silently.

    Returns assembled questions ordered by marks descending, each with
    topic_tag and marks. Also returns total_marks and warnings list.
    """
    async with get_db() as session:
        result = await mock_paper_service.build_mock_paper(
            session=session,
            subject_id=body.subject_id,
            total_marks_target=body.total_marks_target,
            question_type_distribution=body.question_type_distribution,
        )

    return MockPaperResponse(
        questions=[MockPaperQuestionItem(**q) for q in result["questions"]],
        total_marks=result["total_marks"],
        warnings=result["warnings"],
    )
