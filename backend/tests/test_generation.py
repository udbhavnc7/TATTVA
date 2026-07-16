"""
Unit tests for the Grounded Note Generation Service (Task 7.8).

Covers:
  - 2mark / 6mark / 10mark depth — response structure has note_id, confidence, content_md
  - Refusal when max(cosine_similarity) < 0.5 → CoverageInsufficient / router 422
  - LLM failure (GenerationError) → router returns 500, no Note added to session
  - force_regenerate=True → check_hash_changed is NOT called
  - Missing CONFIDENCE line → _parse_confidence_line returns "needs_review"
  - Invalid depth → POST /generate-notes returns 422 (Pydantic validation)
  - topic_id not found → returns 400
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.generation.service import (
    CoverageInsufficient,
    GenerationError,
    VALID_DEPTHS,
    _parse_confidence_line,
    generate_note,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_topic(
    topic_id: uuid.UUID | None = None,
    name: str = "Process Scheduling",
    content_hash: str | None = None,
) -> MagicMock:
    t = MagicMock()
    t.id = topic_id or uuid.uuid4()
    t.name = name
    t.content_hash = content_hash
    t.version = 1
    t.last_updated = datetime.now(timezone.utc)
    t.pending_review = False
    return t


def _make_chunk(similarity: float = 0.85) -> dict:
    return {
        "chunk_id": str(uuid.uuid4()),
        "text": "Relevant lecture content. (Source: lecture.pdf, p.5)",
        "cosine_similarity": similarity,
        "source_filename": "lecture.pdf",
        "page_number": 5,
        "topic_id": str(uuid.uuid4()),
        "module_id": str(uuid.uuid4()),
        "subject_id": str(uuid.uuid4()),
    }


def _make_session(existing_note: MagicMock | None = None) -> AsyncMock:
    """Return an AsyncMock session whose execute chain returns *existing_note*."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(
                return_value=MagicMock(first=MagicMock(return_value=existing_note))
            )
        )
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    return mock_session


def _router_mock_cm(topic: MagicMock | None, gen_result: dict | None = None, gen_side_effect=None):
    """
    Build the (mock_session, mock_cm) pair used for router-level tests.

    topic             — returned by get_topic_by_id (None = not found)
    gen_result        — what gen_service.generate_note returns
    gen_side_effect   — exception to raise instead of returning gen_result
    """
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_cm


# ---------------------------------------------------------------------------
# Fixture: ASGI test client
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ============================================================
# _parse_confidence_line — unit tests (no I/O)
# ============================================================


@pytest.mark.unit
def test_parse_confidence_grounded() -> None:
    """Last line 'CONFIDENCE: grounded' is parsed correctly."""
    content = "Some note paragraph.\n\nCONFIDENCE: grounded"
    assert _parse_confidence_line(content) == "grounded"


@pytest.mark.unit
def test_parse_confidence_partial() -> None:
    """Last line 'CONFIDENCE: partial' is parsed correctly."""
    content = "Note body.\nCONFIDENCE: partial"
    assert _parse_confidence_line(content) == "partial"


@pytest.mark.unit
def test_parse_confidence_needs_review() -> None:
    """Last line 'CONFIDENCE: needs_review' is parsed correctly."""
    content = "Note body.\nCONFIDENCE: needs_review"
    assert _parse_confidence_line(content) == "needs_review"


@pytest.mark.unit
def test_parse_confidence_case_insensitive() -> None:
    """CONFIDENCE: line is matched case-insensitively."""
    assert _parse_confidence_line("Body.\nCONFIDENCE: GROUNDED") == "grounded"


@pytest.mark.unit
def test_parse_confidence_missing_line_returns_needs_review() -> None:
    """When no CONFIDENCE: line is present the safe default 'needs_review' is returned."""
    content = "Note body without any confidence line at the end."
    assert _parse_confidence_line(content) == "needs_review"


@pytest.mark.unit
def test_parse_confidence_malformed_returns_needs_review() -> None:
    """A malformed CONFIDENCE: line falls back to 'needs_review'."""
    content = "Note body.\nCONFIDENCE: maybe"
    assert _parse_confidence_line(content) == "needs_review"


@pytest.mark.unit
def test_parse_confidence_empty_string_returns_needs_review() -> None:
    """Empty content falls back to 'needs_review'."""
    assert _parse_confidence_line("") == "needs_review"


@pytest.mark.unit
def test_parse_confidence_trailing_newlines_ignored() -> None:
    """Trailing newlines after the CONFIDENCE: line do not break parsing."""
    content = "Body.\nCONFIDENCE: partial\n\n\n"
    assert _parse_confidence_line(content) == "partial"


# ============================================================
# generate_note — depth structure tests (service-layer)
# ============================================================

# Common patch targets
_PATCH_GEMINI = "app.services.generation.service._call_gemini"
_PATCH_SEARCH = "app.services.generation.service.semantic_search"
_PATCH_TOPIC = "app.services.generation.service.get_topic_by_id"
_PATCH_VALIDATE = "app.services.generation.service.validate_note"
_PATCH_HASH_CHANGED = "app.services.generation.diff.check_hash_changed"
_PATCH_COMPUTE_HASH = "app.services.generation.diff.compute_topic_hash"
_PATCH_APPLY_BUMP = "app.services.generation.diff.apply_version_bump"


def _llm_output_for(depth: str, badge: str = "grounded") -> str:
    """Return a minimal but structurally valid LLM output for *depth*."""
    if depth == "2mark":
        body = (
            "Process scheduling determines the order of CPU execution. "
            "(Source: lecture.pdf, p.5)"
        )
    elif depth == "6mark":
        body = (
            "**Definition**: Process scheduling is the OS mechanism for allocating CPU time. "
            "(Source: lecture.pdf, p.5)\n\n"
            "**Explanation**: Scheduling algorithms like FCFS and RR differ in wait-time. "
            "(Source: lecture.pdf, p.6)\n\n"
            "**Example**: Round-Robin with quantum=4ms. (Source: lecture.pdf, p.7)"
        )
    else:  # 10mark
        body = (
            "**Definition**: Scheduling is critical for throughput. "
            "(Source: lecture.pdf, p.5)\n\n"
            "**Sub-point 1**: FCFS. (Source: lecture.pdf, p.6)\n\n"
            "**Sub-point 2**: SJF. (Source: lecture.pdf, p.7)\n\n"
            "**Sub-point 3**: Priority. (Source: lecture.pdf, p.8)\n\n"
            "**Worked Example**: Gantt chart. (Source: lecture.pdf, p.9)\n\n"
            "**Diagram**: Mermaid timeline. (Source: lecture.pdf, p.10)\n\n"
            "**Advantages**: Lower avg wait. (Source: lecture.pdf, p.11)"
        )
    return f"{body}\nCONFIDENCE: {badge}"


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", ["2mark", "6mark", "10mark"])
async def test_generate_note_depth_structure(depth: str) -> None:
    """
    For each valid depth, generate_note must return a dict with keys
    note_id, confidence, and content_md.
    """
    topic = _make_topic()
    chunks = [_make_chunk(0.85)]
    llm_out = _llm_output_for(depth, badge="grounded")
    note_id = uuid.uuid4()

    # Build a session that simulates: no existing note → first-time generation
    mock_session = _make_session(existing_note=None)
    # After flush+refresh, the note gets its UUID
    created_note = MagicMock()
    created_note.id = note_id

    def _add_side_effect(obj):
        obj.id = note_id  # simulate DB assigning the PK

    mock_session.add = MagicMock(side_effect=_add_side_effect)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    with (
        patch(_PATCH_TOPIC, new=AsyncMock(return_value=topic)),
        patch(_PATCH_SEARCH, new=AsyncMock(return_value=chunks)),
        patch(_PATCH_GEMINI, new=AsyncMock(return_value=llm_out)),
        patch(_PATCH_VALIDATE, new=AsyncMock(return_value="grounded")),
        patch(_PATCH_COMPUTE_HASH, return_value="a" * 64),
        patch(_PATCH_HASH_CHANGED, return_value=True),
        patch(_PATCH_APPLY_BUMP, new=AsyncMock(return_value=MagicMock())),
    ):
        result = await generate_note(
            session=mock_session,
            topic_id=topic.id,
            depth=depth,
            force_regenerate=False,
        )

    assert "note_id" in result, f"depth={depth}: missing note_id in result"
    assert "confidence" in result, f"depth={depth}: missing confidence in result"
    assert "content_md" in result, f"depth={depth}: missing content_md in result"
    assert isinstance(result["note_id"], str)
    assert result["confidence"] in {"grounded", "partial", "needs_review"}
    assert isinstance(result["content_md"], str)
    assert len(result["content_md"]) > 0


# ============================================================
# CoverageInsufficient — service & router
# ============================================================


@pytest.mark.asyncio
async def test_generate_note_raises_coverage_insufficient_when_low_similarity() -> None:
    """
    When all chunks have cosine_similarity < 0.5, generate_note must raise
    CoverageInsufficient and must NOT call the LLM.
    """
    topic = _make_topic()
    low_chunks = [_make_chunk(0.3), _make_chunk(0.1), _make_chunk(0.49)]
    mock_session = _make_session()

    mock_gemini = AsyncMock()

    with (
        patch(_PATCH_TOPIC, new=AsyncMock(return_value=topic)),
        patch(_PATCH_SEARCH, new=AsyncMock(return_value=low_chunks)),
        patch(_PATCH_GEMINI, new=mock_gemini),
    ):
        with pytest.raises(CoverageInsufficient):
            await generate_note(
                session=mock_session,
                topic_id=topic.id,
                depth="2mark",
            )

    mock_gemini.assert_not_called()


@pytest.mark.asyncio
async def test_generate_note_raises_coverage_insufficient_when_no_chunks() -> None:
    """
    When semantic_search returns an empty list, generate_note must raise
    CoverageInsufficient.
    """
    topic = _make_topic()
    mock_session = _make_session()

    with (
        patch(_PATCH_TOPIC, new=AsyncMock(return_value=topic)),
        patch(_PATCH_SEARCH, new=AsyncMock(return_value=[])),
        patch(_PATCH_GEMINI, new=AsyncMock()),
    ):
        with pytest.raises(CoverageInsufficient):
            await generate_note(
                session=mock_session,
                topic_id=topic.id,
                depth="6mark",
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_returns_422_on_coverage_insufficient(client: AsyncClient) -> None:
    """
    POST /generate-notes must return 422 with coverage_insufficient when
    generate_note raises CoverageInsufficient.
    """
    topic_id = uuid.uuid4()
    mock_topic = _make_topic(topic_id=topic_id)

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.generation.router.get_db", return_value=mock_cm),
        patch(
            "app.services.generation.router.get_topic_by_id",
            new=AsyncMock(return_value=mock_topic),
        ),
        patch(
            "app.services.generation.router.gen_service.generate_note",
            new=AsyncMock(side_effect=CoverageInsufficient("low similarity")),
        ),
    ):
        resp = await client.post(
            "/generate-notes",
            json={"topic_id": str(topic_id), "depth": "2mark"},
        )

    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["error"] == "coverage_insufficient"


# ============================================================
# GenerationError — router returns 500, no Note added
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_returns_500_on_llm_failure_and_no_note_added(
    client: AsyncClient,
) -> None:
    """
    When generate_note raises GenerationError, the router must:
      1. Return HTTP 500.
      2. NOT have added any Note to the session (checked via session.add).
    """
    topic_id = uuid.uuid4()
    mock_topic = _make_topic(topic_id=topic_id)

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.generation.router.get_db", return_value=mock_cm),
        patch(
            "app.services.generation.router.get_topic_by_id",
            new=AsyncMock(return_value=mock_topic),
        ),
        patch(
            "app.services.generation.router.gen_service.generate_note",
            new=AsyncMock(side_effect=GenerationError("API timeout", reason="llm_failure")),
        ),
    ):
        resp = await client.post(
            "/generate-notes",
            json={"topic_id": str(topic_id), "depth": "6mark"},
        )

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"]["error"] == "generation_failed"
    # session.add must NOT have been called — no Note was persisted
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_generate_note_does_not_add_note_on_llm_failure() -> None:
    """
    Service-layer: when _call_gemini raises, generate_note must propagate
    GenerationError and must never call session.add.
    """
    topic = _make_topic()
    chunks = [_make_chunk(0.90)]
    mock_session = _make_session()

    with (
        patch(_PATCH_TOPIC, new=AsyncMock(return_value=topic)),
        patch(_PATCH_SEARCH, new=AsyncMock(return_value=chunks)),
        patch(
            _PATCH_GEMINI,
            new=AsyncMock(side_effect=GenerationError("Gemini down", reason="llm_failure")),
        ),
    ):
        with pytest.raises(GenerationError):
            await generate_note(
                session=mock_session,
                topic_id=topic.id,
                depth="10mark",
            )

    mock_session.add.assert_not_called()


# ============================================================
# force_regenerate=True → check_hash_changed NOT called
# ============================================================


@pytest.mark.asyncio
async def test_force_regenerate_bypasses_hash_check() -> None:
    """
    When force_regenerate=True, check_hash_changed must NOT be called.
    The full pipeline runs unconditionally.
    """
    topic = _make_topic(content_hash="old" * 16)
    chunks = [_make_chunk(0.88)]
    llm_out = _llm_output_for("2mark", badge="grounded")

    mock_session = _make_session(existing_note=None)

    def _add_side_effect(obj):
        obj.id = uuid.uuid4()

    mock_session.add = MagicMock(side_effect=_add_side_effect)

    mock_check_hash = MagicMock(return_value=True)

    with (
        patch(_PATCH_TOPIC, new=AsyncMock(return_value=topic)),
        patch(_PATCH_SEARCH, new=AsyncMock(return_value=chunks)),
        patch(_PATCH_GEMINI, new=AsyncMock(return_value=llm_out)),
        patch(_PATCH_VALIDATE, new=AsyncMock(return_value="grounded")),
        patch(_PATCH_COMPUTE_HASH, return_value="b" * 64),
        patch("app.services.generation.diff.check_hash_changed", mock_check_hash),
        patch(_PATCH_APPLY_BUMP, new=AsyncMock(return_value=MagicMock())),
    ):
        await generate_note(
            session=mock_session,
            topic_id=topic.id,
            depth="2mark",
            force_regenerate=True,
        )

    mock_check_hash.assert_not_called()


# ============================================================
# Topic not found → router 400
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_returns_400_when_topic_not_found(client: AsyncClient) -> None:
    """
    POST /generate-notes must return 400 with invalid_topic_id when the
    topic_id does not resolve to an existing topic.
    """
    missing_topic_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.generation.router.get_db", return_value=mock_cm),
        patch(
            "app.services.generation.router.get_topic_by_id",
            new=AsyncMock(return_value=None),
        ),
    ):
        resp = await client.post(
            "/generate-notes",
            json={"topic_id": str(missing_topic_id), "depth": "2mark"},
        )

    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"] == "invalid_topic_id"


# ============================================================
# Invalid depth → router 422 (Pydantic validation)
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_returns_422_on_invalid_depth(client: AsyncClient) -> None:
    """
    POST /generate-notes with an unrecognized depth value must return 422
    (rejected by the Pydantic field_validator before any service call).
    """
    topic_id = uuid.uuid4()

    resp = await client.post(
        "/generate-notes",
        json={"topic_id": str(topic_id), "depth": "invalid_depth"},
    )

    assert resp.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_returns_422_on_empty_depth(client: AsyncClient) -> None:
    """POST /generate-notes with an empty depth string must return 422."""
    topic_id = uuid.uuid4()

    resp = await client.post(
        "/generate-notes",
        json={"topic_id": str(topic_id), "depth": ""},
    )

    assert resp.status_code == 422


# ============================================================
# Successful generation — router smoke test
# ============================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_generate_notes_success(client: AsyncClient) -> None:
    """
    POST /generate-notes happy path — router returns 200 with note_id,
    confidence, and content_md.
    """
    topic_id = uuid.uuid4()
    note_id = uuid.uuid4()
    mock_topic = _make_topic(topic_id=topic_id)

    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    gen_result = {
        "note_id": str(note_id),
        "confidence": "grounded",
        "content_md": "Study note content. (Source: lecture.pdf, p.5)",
    }

    with (
        patch("app.services.generation.router.get_db", return_value=mock_cm),
        patch(
            "app.services.generation.router.get_topic_by_id",
            new=AsyncMock(return_value=mock_topic),
        ),
        patch(
            "app.services.generation.router.gen_service.generate_note",
            new=AsyncMock(return_value=gen_result),
        ),
    ):
        resp = await client.post(
            "/generate-notes",
            json={"topic_id": str(topic_id), "depth": "2mark"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["note_id"] == str(note_id)
    assert body["confidence"] == "grounded"
    assert "content_md" in body
