"""
Ingestion Service — business logic layer.

Handles:
  - File validation (content-type, size)
  - SHA-256 content-hash computation
  - Duplicate detection
  - Document record creation
  - Document listing and deletion
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE: int = 52_428_800  # 50 MiB in bytes
ALLOWED_CONTENT_TYPE: str = "application/pdf"


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — easy to test with Hypothesis)
# ---------------------------------------------------------------------------


def is_valid_content_type(content_type: str) -> bool:
    """Return True iff *content_type* is exactly 'application/pdf'."""
    return content_type == ALLOWED_CONTENT_TYPE


def is_valid_file_size(size_bytes: int) -> bool:
    """Return True iff *size_bytes* is within the 50 MB limit."""
    return 0 < size_bytes <= MAX_FILE_SIZE


def compute_sha256(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Service functions (require an AsyncSession)
# ---------------------------------------------------------------------------


async def find_document_by_hash(
    session: AsyncSession, content_hash: str
) -> Optional[Document]:
    """Return the first Document whose content_hash matches, or None."""
    result = await session.execute(
        select(Document).where(Document.content_hash == content_hash)
    )
    return result.scalars().first()


async def create_document(
    session: AsyncSession,
    *,
    filename: str,
    content_hash: str,
    subject_id: Optional[uuid.UUID] = None,
) -> Document:
    """
    Persist a new Document record and return it.

    Raises any SQLAlchemy error to the caller — the router is responsible
    for catching storage failures and returning the correct HTTP response.
    """
    doc = Document(
        filename=filename,
        uploaded_at=datetime.now(timezone.utc),
        subject_id=subject_id,
        source_type="manual",
        content_hash=content_hash,
        status="pending",
    )
    session.add(doc)
    await session.flush()   # assigns doc.id; commit is handled by get_db()
    await session.refresh(doc)
    return doc


async def list_documents(session: AsyncSession) -> list[Document]:
    """Return all Document rows ordered by uploaded_at descending."""
    result = await session.execute(
        select(Document).order_by(Document.uploaded_at.desc())
    )
    return list(result.scalars().all())


async def delete_document(
    session: AsyncSession, document_id: uuid.UUID
) -> bool:
    """
    Delete the Document with *document_id*.

    Returns True if a row was deleted, False if no such document exists.
    """
    result = await session.execute(
        delete(Document)
        .where(Document.id == document_id)
        .returning(Document.id)
    )
    deleted_id = result.scalars().first()
    return deleted_id is not None
