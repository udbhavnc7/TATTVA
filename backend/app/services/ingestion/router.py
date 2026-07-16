"""
Ingestion Service router.

Endpoints:
    POST /ingest               — Accept a PDF upload, hash, deduplicate, store
    GET  /documents            — List all ingested documents
    DELETE /documents/{id}     — Remove a document
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.session import get_db
from app.services.ingestion.service import (
    compute_sha256,
    create_document,
    delete_document,
    find_document_by_hash,
    is_valid_content_type,
    is_valid_file_size,
    list_documents,
)

router = APIRouter(tags=["ingestion"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    uploaded_at: str
    subject_id: Optional[uuid.UUID]
    source_type: str
    content_hash: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/ingest/health")
async def health() -> dict:
    """Health-check for the Ingestion Service."""
    return {"service": "ingestion", "status": "ok"}


@router.post("/ingest", status_code=200)
async def ingest_document(
    file: UploadFile = File(...),
    subject_id: Optional[uuid.UUID] = Form(None),
) -> JSONResponse:
    """
    Accept a PDF upload, compute its SHA-256 hash, deduplicate, and store.

    Returns:
        200 { document_id: UUID }             — new document stored
        400 { error: "file_type_invalid" }    — wrong MIME type
        400 { error: "file_size_exceeded" }   — file > 50 MB
        409 { error: "duplicate_content",
              existing_document_id: UUID }    — hash collision
    """
    # --- 2.1  Validate content-type ---
    content_type = file.content_type or ""
    if not is_valid_content_type(content_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "file_type_invalid"},
        )

    # --- 2.1  Read bytes and validate size ---
    file_bytes = await file.read()
    if not is_valid_file_size(len(file_bytes)):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "file_size_exceeded"},
        )

    # --- 2.2  Compute SHA-256 ---
    content_hash = compute_sha256(file_bytes)

    async with get_db() as session:
        # --- 2.3  Duplicate detection ---
        existing = await find_document_by_hash(session, content_hash)
        if existing is not None:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error": "duplicate_content",
                    "existing_document_id": str(existing.id),
                },
            )

        # --- 2.2  Persist document record ---
        try:
            doc = await create_document(
                session,
                filename=file.filename or "upload.pdf",
                content_hash=content_hash,
                subject_id=subject_id,
            )
        except Exception as exc:
            # Storage failure: surface error, guarantee no partial record
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage failure; document was not saved.",
            ) from exc

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"document_id": str(doc.id)},
    )


@router.get("/documents", status_code=200)
async def get_documents() -> list[dict]:
    """
    Return all ingested documents ordered by uploaded_at descending.

    Response items: { id, filename, uploaded_at, subject_id,
                      source_type, content_hash }
    """
    async with get_db() as session:
        docs = await list_documents(session)

    return [
        {
            "id": str(d.id),
            "filename": d.filename,
            "uploaded_at": d.uploaded_at.isoformat(),
            "subject_id": str(d.subject_id) if d.subject_id else None,
            "source_type": d.source_type,
            "content_hash": d.content_hash,
        }
        for d in docs
    ]


@router.delete("/documents/{document_id}", status_code=204)
async def remove_document(document_id: uuid.UUID) -> None:
    """
    Delete the specified document.

    Returns 204 on success, 404 if the document does not exist.
    """
    async with get_db() as session:
        deleted = await delete_document(session, document_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found.",
        )
