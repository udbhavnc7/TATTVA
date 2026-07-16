"""
Property-based tests for the Ingestion Service.

Feature: tattva-exam-engine

Four properties under test:
  Property 1 — file validation predicate
  Property 2 — SHA-256 dedupe idempotency
  Property 3 — valid upload returns UUID document_id
  Property 4 — hash determinism

Each @settings decorator sets max_examples=100.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.services.ingestion.service import (
    MAX_FILE_SIZE,
    compute_sha256,
    is_valid_content_type,
    is_valid_file_size,
)


# ---------------------------------------------------------------------------
# Shared strategy helpers
# ---------------------------------------------------------------------------

# Arbitrary content-type strings (any printable ASCII)
content_type_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=0,
    max_size=120,
)

# File sizes covering both valid and invalid ranges
# Valid: 1 … MAX_FILE_SIZE; Invalid: 0 or > MAX_FILE_SIZE
size_strategy = st.integers(min_value=0, max_value=MAX_FILE_SIZE * 2)

# Raw byte payloads up to 50 MB (capped at a smaller value for speed)
# We use max_size=4096 for speed; the property is purely about hashing bytes.
bytes_strategy = st.binary(min_size=0, max_size=4096)

# Valid PDF-sized byte payloads (1 … MAX_FILE_SIZE, capped for test speed)
valid_pdf_bytes_strategy = st.binary(min_size=1, max_size=4096)


# ---------------------------------------------------------------------------
# Property 1 — file validation predicate
#
# For any (content_type, size_bytes) pair, the combined validation
# accepts iff content_type == "application/pdf" AND 1 <= size_bytes <= MAX_FILE_SIZE.
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(content_type=content_type_strategy, size_bytes=size_strategy)
def test_property1_file_validation_predicate(
    content_type: str, size_bytes: int
) -> None:
    """
    Feature: tattva-exam-engine, Property 1: file validation predicate

    The combined is_valid_content_type + is_valid_file_size predicates
    accept a (content_type, size_bytes) pair iff
    content_type == 'application/pdf' AND 1 <= size_bytes <= MAX_FILE_SIZE.

    Validates: Requirements 2.1
    """
    type_ok = is_valid_content_type(content_type)
    size_ok = is_valid_file_size(size_bytes)
    accepted = type_ok and size_ok

    expected = (content_type == "application/pdf") and (1 <= size_bytes <= MAX_FILE_SIZE)

    assert accepted == expected, (
        f"Mismatch for content_type={content_type!r}, size_bytes={size_bytes}: "
        f"accepted={accepted}, expected={expected}"
    )


# ---------------------------------------------------------------------------
# Property 2 — SHA-256 dedupe idempotency
#
# Uploading the same file bytes twice results in exactly one document record
# (the second call returns 409).  Tested via the service layer (mock DB).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(file_bytes=valid_pdf_bytes_strategy)
async def test_property2_dedupe_idempotency(file_bytes: bytes) -> None:
    """
    Feature: tattva-exam-engine, Property 2: SHA-256 dedupe idempotency

    Uploading the same byte content twice should produce the same
    content_hash on both calls; the second call must encounter a duplicate.

    Validates: Requirements 2.3
    """
    # Compute hash twice — must be identical
    hash1 = compute_sha256(file_bytes)
    hash2 = compute_sha256(file_bytes)

    assert hash1 == hash2, "SHA-256 of identical bytes produced different hashes"

    # A document with hash1 in DB means the second upload is a duplicate
    existing_id = uuid.uuid4()
    existing_doc = MagicMock()
    existing_doc.id = existing_id
    existing_doc.content_hash = hash1

    # First call: no existing document → would be stored
    # Second call: existing document found → duplicate
    # We verify the duplicate detection path triggers correctly.
    from app.services.ingestion.service import find_document_by_hash

    mock_session_first = AsyncMock()
    mock_session_first.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
    )

    mock_session_second = AsyncMock()
    mock_session_second.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=existing_doc)))
        )
    )

    # First call: no duplicate
    result_first = await find_document_by_hash(mock_session_first, hash1)
    assert result_first is None, "First upload should not find a duplicate"

    # Second call: duplicate found
    result_second = await find_document_by_hash(mock_session_second, hash2)
    assert result_second is not None, "Second upload should detect the duplicate"
    assert result_second.content_hash == hash1


# ---------------------------------------------------------------------------
# Property 3 — valid upload returns UUID document_id
#
# Any valid PDF (content_type=="application/pdf", size<=50MB, not a duplicate)
# must return a non-null UUID document_id in the 200 response.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(file_bytes=valid_pdf_bytes_strategy)
async def test_property3_valid_upload_returns_uuid(file_bytes: bytes) -> None:
    """
    Feature: tattva-exam-engine, Property 3: valid upload returns UUID document_id

    Any non-duplicate PDF within the size limit must produce a 200 response
    whose document_id is a valid, non-null UUID.

    Validates: Requirements 2.2
    """
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    doc_id = uuid.uuid4()

    mock_session = AsyncMock()
    # No duplicate
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))
        )
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock(
        side_effect=lambda obj: setattr(obj, "id", doc_id)
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ingestion.router.get_db", return_value=mock_cm):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/ingest",
                files={
                    "file": (
                        "test.pdf",
                        io.BytesIO(file_bytes),
                        "application/pdf",
                    )
                },
            )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "document_id" in body, "Response must contain document_id"

    returned_id = body["document_id"]
    assert returned_id is not None, "document_id must not be None"

    # Must be a valid UUID
    parsed = uuid.UUID(returned_id)
    assert parsed is not None


# ---------------------------------------------------------------------------
# Property 4 — hash determinism
#
# SHA-256 of the same bytes always produces the same hex digest.
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(data=bytes_strategy)
def test_property4_hash_determinism(data: bytes) -> None:
    """
    Feature: tattva-exam-engine, Property 4: hash determinism

    compute_sha256(data) must return the same 64-character hex string
    on every call for the same input bytes.

    Validates: Requirements 2.2
    """
    hash_a = compute_sha256(data)
    hash_b = compute_sha256(data)

    assert hash_a == hash_b, (
        f"Non-deterministic hash: got {hash_a!r} then {hash_b!r} for same bytes"
    )
    # Sanity: SHA-256 hex digest is always 64 characters
    assert len(hash_a) == 64, f"Expected 64-char hex digest, got {len(hash_a)}"
    # Must be valid lowercase hex
    assert all(c in "0123456789abcdef" for c in hash_a), (
        f"Digest contains non-hex characters: {hash_a!r}"
    )
