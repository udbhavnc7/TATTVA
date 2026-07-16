"""
Parsing Service router — Task 3.4

Endpoints:
    GET  /parse/health                  — health check
    POST /parse/{document_id}           — trigger parsing for an ingested document
"""

from __future__ import annotations

import uuid
import logging

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.services.parsing.service import parse_document, store_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parse", tags=["parsing"])


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

async def get_session() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ParseResponse(BaseModel):
    document_id: uuid.UUID
    chunks_stored: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    """Health check for the Parsing Service."""
    return {"service": "parsing", "status": "ok"}


@router.post("/{document_id}", response_model=ParseResponse)
async def trigger_parsing(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ParseResponse:
    """Parse the uploaded PDF and store resulting chunks in the Knowledge Store.

    - Accepts a PDF upload as multipart/form-data.
    - Extracts text using PyMuPDF (+ OCR fallback for image-only pages).
    - Splits text into 400–600-token chunks with page attribution.
    - Stores chunks atomically; rolls back and returns 500 on any write failure.
    """
    content_type = file.content_type or ""
    if "pdf" not in content_type.lower():
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        chunks = parse_document(document_id, file_bytes)
    except Exception as exc:
        logger.error("Parsing failed for document_id=%s: %s", document_id, exc)
        raise HTTPException(
            status_code=422, detail=f"PDF parsing failed: {exc}"
        ) from exc

    try:
        await store_chunks(session, chunks)
        await session.commit()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ParseResponse(document_id=document_id, chunks_stored=len(chunks))
