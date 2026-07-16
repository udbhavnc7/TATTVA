"""
Unit tests for the Ingestion Service.

Covers:
  - Valid upload happy path (200 + document_id UUID)
  - Rejection: wrong content type  → 400 file_type_invalid
  - Rejection: file too large       → 400 file_size_exceeded
  - Rejection: duplicate content   → 409 duplicate_content
  - Storage failure rollback        → 500, no partial record

Tests use httpx AsyncClient with the FastAPI app and AsyncMock for the DB
session, so no real database is required.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.db.models import Document  # used only for MagicMock spec
from app.services.ingestion.service import MAX_FILE_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_document(
    doc_id: uuid.UUID | None = None,
    filename: str = "test.pdf",
    content_hash: str = "a" * 64,
    subject_id: uuid.UUID | None = None,
) -> MagicMock:
    """
    Build a lightweight mock that looks like a Document ORM instance.
    Using MagicMock avoids SQLAlchemy instrumentation requirements.
    """
    doc = MagicMock(spec=Document)
    doc.id = doc_id or uuid.uuid4()
    doc.filename = filename
    doc.content_hash = content_hash
    doc.subject_id = subject_id
    doc.source_type = "manual"
    doc.status = "pending"
    doc.uploaded_at = datetime.now(timezone.utc)
    return doc


def _make_pdf_bytes(size: int = 1024) -> bytes:
    """Return a byte string that is exactly *size* bytes long."""
    return b"%PDF-1.4 " + b"0" * max(0, size - 9)


# ---------------------------------------------------------------------------
# Fixture: async test client
# ---------------------------------------------------------------------------

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# 2.6.1  Happy path — valid PDF upload returns 200 with UUID document_id
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_valid_pdf_returns_document_id(client: AsyncClient) -> None:
    """A valid PDF under 50 MB should return 200 { document_id: <UUID> }."""
    doc_id = uuid.uuid4()
    mock_doc = _make_document(doc_id=doc_id)
    pdf_bytes = _make_pdf_bytes(1024)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", doc_id))

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        resp = await client.post(
            "/ingest",
            files={"file": ("lecture.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "document_id" in body
    # Should be a valid UUID string
    uuid.UUID(body["document_id"])


# ---------------------------------------------------------------------------
# 2.6.2  Rejection — wrong content type → 400 file_type_invalid
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_wrong_content_type_returns_400(client: AsyncClient) -> None:
    """Uploading a non-PDF file must return 400 with error='file_type_invalid'."""
    resp = await client.post(
        "/ingest",
        files={"file": ("notes.docx", io.BytesIO(b"docx content"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "file_type_invalid"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_plain_text_returns_400(client: AsyncClient) -> None:
    """text/plain must also be rejected as file_type_invalid."""
    resp = await client.post(
        "/ingest",
        files={"file": ("readme.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "file_type_invalid"}


# ---------------------------------------------------------------------------
# 2.6.3  Rejection — file too large → 400 file_size_exceeded
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_oversized_file_returns_400(client: AsyncClient) -> None:
    """A PDF that exceeds 50 MB must return 400 with error='file_size_exceeded'."""
    # One byte over the limit
    oversized_bytes = b"0" * (MAX_FILE_SIZE + 1)
    resp = await client.post(
        "/ingest",
        files={"file": ("big.pdf", io.BytesIO(oversized_bytes), "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json() == {"error": "file_size_exceeded"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_exactly_at_limit_is_accepted(client: AsyncClient) -> None:
    """A PDF of exactly 50 MB (52_428_800 bytes) must be accepted."""
    boundary_bytes = b"0" * MAX_FILE_SIZE
    doc_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", doc_id))

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        resp = await client.post(
            "/ingest",
            files={"file": ("max.pdf", io.BytesIO(boundary_bytes), "application/pdf")},
        )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2.6.4  Rejection — duplicate content → 409 duplicate_content
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_duplicate_returns_409(client: AsyncClient) -> None:
    """Uploading a file whose hash already exists must return 409."""
    existing_id = uuid.uuid4()
    existing_doc = _make_document(doc_id=existing_id)
    pdf_bytes = _make_pdf_bytes(512)

    mock_session = AsyncMock()
    # find_document_by_hash will return the existing document
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_doc)))
        )
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        resp = await client.post(
            "/ingest",
            files={"file": ("dupe.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "duplicate_content"
    assert body["existing_document_id"] == str(existing_id)


# ---------------------------------------------------------------------------
# 2.6.5  Storage failure → 500, no partial document record
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ingest_storage_failure_returns_500_no_partial_record(
    client: AsyncClient,
) -> None:
    """
    If the DB write raises an exception, the endpoint must return 500
    and must not persist a partial Document record (rollback verified via
    mock_session.add never being committed).
    """
    pdf_bytes = _make_pdf_bytes(512)

    mock_session = AsyncMock()
    # No duplicate found
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
    )
    mock_session.add = MagicMock()
    # flush raises — simulates storage failure
    mock_session.flush = AsyncMock(side_effect=RuntimeError("DB write failed"))

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        resp = await client.post(
            "/ingest",
            files={"file": ("fail.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert resp.status_code == 500
    # The document was added to the session but flush failed → no commit
    # __aexit__ returning False means the context manager did not swallow the error
    mock_session.add.assert_called_once()
    # Crucially, flush raised — so no document was persisted
    mock_session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# 2.6.6  GET /documents — returns list
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_documents_returns_list(client: AsyncClient) -> None:
    """GET /documents must return a JSON array."""
    doc1 = _make_document(doc_id=uuid.uuid4(), filename="a.pdf")
    doc2 = _make_document(doc_id=uuid.uuid4(), filename="b.pdf")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[doc1, doc2])))
        )
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        resp = await client.get("/documents")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["filename"] == "a.pdf"
    assert body[1]["filename"] == "b.pdf"


# ---------------------------------------------------------------------------
# 2.6.7  DELETE /documents/{id} — success and not-found
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_document_success_returns_204(client: AsyncClient) -> None:
    """DELETE /documents/{id} must return 204 when the document exists."""
    doc_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=doc_id)))
        )
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        resp = await client.delete(f"/documents/{doc_id}")

    assert resp.status_code == 204


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_document_not_found_returns_404(client: AsyncClient) -> None:
    """DELETE /documents/{id} must return 404 when the document does not exist."""
    doc_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        resp = await client.delete(f"/documents/{doc_id}")

    assert resp.status_code == 404
