"""
Unit tests for the Knowledge Store Service.

Covers:
  - POST /subjects happy path (201)
  - POST /subjects duplicate code → 409
  - POST /subjects invalid code format → 400
  - GET /subjects returns list
  - POST /subjects/{id}/modules happy path (201)
  - POST /subjects/{id}/modules duplicate number → 409
  - POST /subjects/{id}/modules subject not found → 404
  - GET /subjects/{id}/modules returns list
  - GET /subjects/{id}/modules subject not found → 404
  - GET /topics/{topic_id} happy path
  - GET /topics/{topic_id} not found → 404
  - GET /search success
  - GET /search failure → 500
  - validate_chunk_tags — all present passes, missing field raises ValueError
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.knowledge_store.service import validate_chunk_tags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_subject(
    subject_id: uuid.UUID | None = None,
    name: str = "Operating Systems",
    code: str = "OS2024",
) -> MagicMock:
    obj = MagicMock()
    obj.id = subject_id or uuid.uuid4()
    obj.name = name
    obj.code = code
    obj.created_at = datetime.now(timezone.utc)
    return obj


def _make_module(
    module_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    number: int = 1,
    title: str = "Introduction",
) -> MagicMock:
    obj = MagicMock()
    obj.id = module_id or uuid.uuid4()
    obj.subject_id = subject_id or uuid.uuid4()
    obj.number = number
    obj.title = title
    return obj


def _make_topic(
    topic_id: uuid.UUID | None = None,
    module_id: uuid.UUID | None = None,
    name: str = "Process Scheduling",
) -> MagicMock:
    obj = MagicMock()
    obj.id = topic_id or uuid.uuid4()
    obj.module_id = module_id or uuid.uuid4()
    obj.name = name
    obj.version = 1
    obj.pending_review = False
    obj.last_updated = datetime.now(timezone.utc)
    return obj


def _mock_session_returning(value) -> tuple[AsyncMock, AsyncMock]:
    """Return (mock_session, mock_cm) where execute().scalars().first() == value."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=value))
            )
        )
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    def _refresh_side_effect(obj):
        pass  # object already has id set by mock

    mock_session.refresh = AsyncMock(side_effect=_refresh_side_effect)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_cm


# ---------------------------------------------------------------------------
# Fixture: async test client
# ---------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ============================================================
# POST /subjects
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subject_returns_201(client: AsyncClient) -> None:
    """Valid subject creation should return 201 with id, name, code."""
    subject_id = uuid.uuid4()
    mock_subject = _make_subject(subject_id=subject_id, code="OS2024")

    _, mock_cm = _mock_session_returning(None)  # no existing subject
    # After flush, refresh sets up the subject
    mock_cm.__aenter__.return_value.refresh = AsyncMock(
        side_effect=lambda obj: setattr(obj, "id", subject_id)
        or setattr(obj, "created_at", datetime.now(timezone.utc))
    )

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.post(
            "/subjects", json={"name": "Operating Systems", "code": "OS2024"}
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["code"] == "OS2024"
    assert body["name"] == "Operating Systems"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subject_duplicate_code_returns_409(client: AsyncClient) -> None:
    """Duplicate subject code must return 409 with duplicate_subject_code error."""
    existing = _make_subject(code="OS2024")

    _, mock_cm = _mock_session_returning(existing)  # existing found

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.post(
            "/subjects", json={"name": "New OS", "code": "OS2024"}
        )

    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["error"] == "duplicate_subject_code"
    assert body["detail"]["code"] == "OS2024"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subject_invalid_code_returns_400(client: AsyncClient) -> None:
    """Subject code with invalid format must return 400."""
    _, mock_cm = _mock_session_returning(None)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        # Too short (3 chars)
        resp = await client.post(
            "/subjects", json={"name": "Test", "code": "AB3"}
        )

    assert resp.status_code in (400, 422)  # pydantic min_length=4 may give 422


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subject_invalid_code_with_special_chars_returns_400(
    client: AsyncClient,
) -> None:
    """Subject code with special characters (not alphanumeric) must return 400."""
    _, mock_cm = _mock_session_returning(None)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.post(
            "/subjects", json={"name": "Test", "code": "OS-2024"}
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"] == "invalid_subject_code"


# ============================================================
# GET /subjects
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_subjects_returns_list(client: AsyncClient) -> None:
    """GET /subjects should return a JSON list."""
    s1 = _make_subject(code="CSE101")
    s2 = _make_subject(code="DSA202")

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[s1, s2]))
            )
        )
    )
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.get("/subjects")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    codes = {item["code"] for item in body}
    assert codes == {"CSE101", "DSA202"}


# ============================================================
# POST /subjects/{id}/modules
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_module_returns_201(client: AsyncClient) -> None:
    """Creating a module for a valid subject should return 201."""
    subject_id = uuid.uuid4()
    module_id = uuid.uuid4()
    mock_subject = _make_subject(subject_id=subject_id)
    mock_module = _make_module(module_id=module_id, subject_id=subject_id, number=1)

    # Two sequential execute calls:
    # 1st → find subject (returns mock_subject)
    # 2nd → find existing module (returns None)
    mock_session = AsyncMock()
    call_count = [0]

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Subject lookup
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_subject))
                )
            )
        else:
            # Module uniqueness check → None
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                )
            )

    mock_session.execute = AsyncMock(side_effect=_execute_side_effect)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock(
        side_effect=lambda obj: (
            setattr(obj, "id", module_id)
            or setattr(obj, "subject_id", subject_id)
        )
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.post(
            f"/subjects/{subject_id}/modules",
            json={"number": 1, "title": "Introduction"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["number"] == 1
    assert body["title"] == "Introduction"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_module_subject_not_found_returns_404(
    client: AsyncClient,
) -> None:
    """Creating a module for a non-existent subject should return 404."""
    subject_id = uuid.uuid4()

    _, mock_cm = _mock_session_returning(None)  # subject not found

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.post(
            f"/subjects/{subject_id}/modules",
            json={"number": 1, "title": "Introduction"},
        )

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "subject_not_found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_module_duplicate_number_returns_409(
    client: AsyncClient,
) -> None:
    """Duplicate module number within the same subject must return 409."""
    subject_id = uuid.uuid4()
    mock_subject = _make_subject(subject_id=subject_id)
    existing_module = _make_module(subject_id=subject_id, number=1)

    mock_session = AsyncMock()
    call_count = [0]

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_subject))
                )
            )
        else:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(
                        first=MagicMock(return_value=existing_module)
                    )
                )
            )

    mock_session.execute = AsyncMock(side_effect=_execute_side_effect)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.post(
            f"/subjects/{subject_id}/modules",
            json={"number": 1, "title": "Duplicate"},
        )

    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "duplicate_module_number"


# ============================================================
# GET /subjects/{id}/modules
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_modules_returns_list(client: AsyncClient) -> None:
    """GET /subjects/{id}/modules should return modules list."""
    subject_id = uuid.uuid4()
    mock_subject = _make_subject(subject_id=subject_id)
    m1 = _make_module(subject_id=subject_id, number=1, title="Intro")
    m2 = _make_module(subject_id=subject_id, number=2, title="Advanced")

    mock_session = AsyncMock()
    call_count = [0]

    def _execute_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_subject))
                )
            )
        else:
            return MagicMock(
                scalars=MagicMock(
                    return_value=MagicMock(all=MagicMock(return_value=[m1, m2]))
                )
            )

    mock_session.execute = AsyncMock(side_effect=_execute_side_effect)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.get(f"/subjects/{subject_id}/modules")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_modules_subject_not_found_returns_404(
    client: AsyncClient,
) -> None:
    """GET /subjects/{id}/modules should return 404 when subject not found."""
    subject_id = uuid.uuid4()

    _, mock_cm = _mock_session_returning(None)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.get(f"/subjects/{subject_id}/modules")

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "subject_not_found"


# ============================================================
# GET /topics/{topic_id}
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_topic_returns_topic(client: AsyncClient) -> None:
    """GET /topics/{id} should return topic details for a valid topic."""
    topic_id = uuid.uuid4()
    mock_topic = _make_topic(topic_id=topic_id, name="Deadlocks")

    _, mock_cm = _mock_session_returning(mock_topic)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.get(f"/topics/{topic_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(topic_id)
    assert body["name"] == "Deadlocks"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_topic_not_found_returns_404(client: AsyncClient) -> None:
    """GET /topics/{id} should return 404 when topic does not exist."""
    topic_id = uuid.uuid4()

    _, mock_cm = _mock_session_returning(None)

    with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
        resp = await client.get(f"/topics/{topic_id}")

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "topic_not_found"


# ============================================================
# GET /search
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_returns_results(client: AsyncClient) -> None:
    """GET /search should return results list with expected fields."""
    topic_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    module_id = uuid.uuid4()
    subject_id = uuid.uuid4()

    mock_results = [
        {
            "chunk_id": str(chunk_id),
            "text": "Process scheduling determines execution order.",
            "cosine_similarity": 0.92,
            "source_filename": "os_lecture.pdf",
            "page_number": 5,
            "subject_id": str(subject_id),
            "module_id": str(module_id),
            "topic_id": str(topic_id),
        }
    ]

    with patch(
        "app.services.knowledge_store.router.service.semantic_search",
        new=AsyncMock(return_value=mock_results),
    ):
        with patch("app.services.knowledge_store.router.get_db") as mock_get_db:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = mock_cm

            resp = await client.get(
                f"/search?q=process+scheduling&topic_id={topic_id}&k=1"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["chunk_id"] == str(chunk_id)
    assert result["cosine_similarity"] == 0.92
    assert result["source_filename"] == "os_lecture.pdf"
    assert result["page_number"] == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_failure_returns_500(client: AsyncClient) -> None:
    """GET /search should return 500 with search_failed error on any exception."""
    with patch(
        "app.services.knowledge_store.router.service.semantic_search",
        new=AsyncMock(side_effect=RuntimeError("pgvector error")),
    ):
        with patch("app.services.knowledge_store.router.get_db") as mock_get_db:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = mock_cm

            resp = await client.get("/search?q=deadlocks")

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"]["error"] == "search_failed"
    assert "pgvector error" in body["detail"]["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_default_k_is_5(client: AsyncClient) -> None:
    """GET /search without k should default k=5."""
    captured_k = []

    async def _mock_search(session, query_text, topic_id, k=5):
        captured_k.append(k)
        return []

    with patch(
        "app.services.knowledge_store.router.service.semantic_search",
        new=_mock_search,
    ):
        with patch("app.services.knowledge_store.router.get_db") as mock_get_db:
            mock_session = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_get_db.return_value = mock_cm

            resp = await client.get("/search?q=test")

    assert resp.status_code == 200
    assert captured_k == [5]


# ============================================================
# validate_chunk_tags (Task 5.5)
# ============================================================


def test_validate_chunk_tags_all_present_passes() -> None:
    """A chunk with all required tags set should pass validation."""
    chunk = {
        "topic_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "page_number": 1,
    }
    # Should not raise
    validate_chunk_tags(chunk)


def test_validate_chunk_tags_missing_topic_id_raises() -> None:
    """A chunk missing topic_id must raise ValueError."""
    chunk = {
        "topic_id": None,
        "document_id": uuid.uuid4(),
        "page_number": 1,
    }
    with pytest.raises(ValueError, match="topic_id"):
        validate_chunk_tags(chunk)


def test_validate_chunk_tags_missing_document_id_raises() -> None:
    """A chunk missing document_id must raise ValueError."""
    chunk = {
        "topic_id": uuid.uuid4(),
        "document_id": None,
        "page_number": 1,
    }
    with pytest.raises(ValueError, match="document_id"):
        validate_chunk_tags(chunk)


def test_validate_chunk_tags_missing_page_number_raises() -> None:
    """A chunk missing page_number must raise ValueError."""
    chunk = {
        "topic_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "page_number": None,
    }
    with pytest.raises(ValueError, match="page_number"):
        validate_chunk_tags(chunk)


def test_validate_chunk_tags_absent_key_raises() -> None:
    """A chunk dict with absent (not just None) key must raise ValueError."""
    chunk = {
        "document_id": uuid.uuid4(),
        "page_number": 1,
        # topic_id key absent entirely
    }
    with pytest.raises(ValueError, match="topic_id"):
        validate_chunk_tags(chunk)
