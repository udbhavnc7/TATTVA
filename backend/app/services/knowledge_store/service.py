"""
Knowledge Store Service — business logic layer.

Covers:
  - Subject CRUD  (POST /subjects, GET /subjects)
  - Module CRUD   (POST /subjects/{id}/modules, GET /subjects/{id}/modules)
  - Topic detail  (GET /topics/{topic_id})
  - Semantic search (GET /search?q=&topic_id=&k=)
  - Chunk tag enforcement (validate_chunk_tags)
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Module, Subject, Topic

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_CODE_RE = re.compile(r"^[A-Za-z0-9]{4,10}$")


def validate_subject_code(code: str) -> bool:
    """Return True if *code* is 4–10 alphanumeric characters."""
    return bool(_CODE_RE.match(code))


# ---------------------------------------------------------------------------
# Chunk tag enforcement (Task 5.5)
# ---------------------------------------------------------------------------

REQUIRED_CHUNK_TAGS = ("topic_id", "document_id", "page_number")


def validate_chunk_tags(chunk: dict[str, Any]) -> None:
    """
    Raise ValueError if any required chunk tag is None or missing.

    Required tags (service-layer enforcement, not DB constraints):
      topic_id, document_id, page_number

    Note: subject_id and module_id are resolved via topic→module→subject
    join at query time; they are NOT columns on the chunks table.

    Raises
    ------
    ValueError
        With a message identifying the first missing/null tag.
    """
    for tag in REQUIRED_CHUNK_TAGS:
        if chunk.get(tag) is None:
            raise ValueError(f"Chunk is missing required tag: '{tag}'")


# ---------------------------------------------------------------------------
# Subject operations
# ---------------------------------------------------------------------------


async def get_all_subjects(session: AsyncSession) -> list[Subject]:
    """Return all subjects ordered by created_at."""
    result = await session.execute(select(Subject).order_by(Subject.created_at))
    return list(result.scalars().all())


async def get_subject_by_id(session: AsyncSession, subject_id: uuid.UUID) -> Subject | None:
    """Return a Subject by primary key, or None if not found."""
    result = await session.execute(select(Subject).where(Subject.id == subject_id))
    return result.scalars().first()


async def get_subject_by_code(session: AsyncSession, code: str) -> Subject | None:
    """Return a Subject matching *code* (case-sensitive), or None."""
    result = await session.execute(select(Subject).where(Subject.code == code))
    return result.scalars().first()


async def create_subject(
    session: AsyncSession, name: str, code: str
) -> Subject:
    """
    Create and persist a new Subject.

    Parameters
    ----------
    session:
        Active async SQLAlchemy session.
    name:
        Subject name (1–120 characters).
    code:
        Subject code (4–10 alphanumeric characters); must be unique.

    Returns
    -------
    Subject
        The newly created and flushed Subject ORM instance.

    Raises
    ------
    ValueError
        If *code* fails the format check.
    """
    if not validate_subject_code(code):
        raise ValueError(
            f"Subject code '{code}' must be 4–10 alphanumeric characters."
        )

    subject = Subject(name=name, code=code)
    session.add(subject)
    await session.flush()
    await session.refresh(subject)
    return subject


# ---------------------------------------------------------------------------
# Module operations
# ---------------------------------------------------------------------------


async def get_modules_for_subject(
    session: AsyncSession, subject_id: uuid.UUID
) -> list[Module]:
    """Return all modules for a subject ordered by number."""
    result = await session.execute(
        select(Module)
        .where(Module.subject_id == subject_id)
        .order_by(Module.number)
    )
    return list(result.scalars().all())


async def get_module_by_subject_and_number(
    session: AsyncSession, subject_id: uuid.UUID, number: int
) -> Module | None:
    """Return a Module matching (subject_id, number), or None."""
    result = await session.execute(
        select(Module).where(
            Module.subject_id == subject_id,
            Module.number == number,
        )
    )
    return result.scalars().first()


async def create_module(
    session: AsyncSession,
    subject_id: uuid.UUID,
    number: int,
    title: str,
) -> Module:
    """
    Create and persist a new Module for a given Subject.

    Returns
    -------
    Module
        The newly created and flushed Module ORM instance.
    """
    module = Module(subject_id=subject_id, number=number, title=title)
    session.add(module)
    await session.flush()
    await session.refresh(module)
    return module


# ---------------------------------------------------------------------------
# Topic operations
# ---------------------------------------------------------------------------


async def get_topic_by_id(
    session: AsyncSession, topic_id: uuid.UUID
) -> Topic | None:
    """Return a Topic by primary key, or None."""
    result = await session.execute(select(Topic).where(Topic.id == topic_id))
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Semantic search (Task 5.4)
# ---------------------------------------------------------------------------


async def semantic_search(
    session: AsyncSession,
    query_text: str,
    topic_id: uuid.UUID | None,
    k: int = 5,
) -> list[dict[str, Any]]:
    """
    Run a pgvector cosine-similarity search over the chunks table.

    The embedding for *query_text* is generated via
    ``app.db.vector_utils.generate_embedding``.

    Parameters
    ----------
    session:
        Active async SQLAlchemy session.
    query_text:
        The raw text query to embed and search.
    topic_id:
        When provided, results are filtered to chunks belonging to this topic.
    k:
        Maximum number of results to return (default 5).

    Returns
    -------
    list[dict]
        Sorted descending by cosine_similarity; each dict contains:
        chunk_id, text, cosine_similarity, source_filename,
        page_number, subject_id, module_id, topic_id.

    Raises
    ------
    Exception
        Any exception is allowed to propagate — the router wraps this in a
        500 response.
    """
    from app.db.vector_utils import generate_embedding

    embedding = generate_embedding(query_text)
    # Convert to the string representation pgvector expects.
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

    # Build the query; filter by topic_id when provided.
    if topic_id is not None:
        sql = text(
            """
            SELECT
                c.id          AS chunk_id,
                c.text        AS text,
                c.page_number AS page_number,
                c.document_id AS document_id,
                c.topic_id    AS topic_id,
                (c.embedding <=> CAST(:query_vec AS vector)) AS cosine_distance,
                d.filename    AS source_filename,
                t.module_id   AS module_id,
                mo.subject_id AS subject_id
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN topics    t  ON t.id = c.topic_id
            JOIN modules   mo ON mo.id = t.module_id
            WHERE c.topic_id = :topic_id
            ORDER BY cosine_distance ASC
            LIMIT :k
            """
        )
        rows = await session.execute(
            sql,
            {"query_vec": vec_str, "topic_id": str(topic_id), "k": k},
        )
    else:
        sql = text(
            """
            SELECT
                c.id          AS chunk_id,
                c.text        AS text,
                c.page_number AS page_number,
                c.document_id AS document_id,
                c.topic_id    AS topic_id,
                (c.embedding <=> CAST(:query_vec AS vector)) AS cosine_distance,
                d.filename    AS source_filename,
                t.module_id   AS module_id,
                mo.subject_id AS subject_id
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN topics    t  ON t.id = c.topic_id
            JOIN modules   mo ON mo.id = t.module_id
            ORDER BY cosine_distance ASC
            LIMIT :k
            """
        )
        rows = await session.execute(sql, {"query_vec": vec_str, "k": k})

    results = []
    for row in rows.mappings():
        cosine_distance = float(row["cosine_distance"])
        cosine_similarity = 1.0 - cosine_distance
        results.append(
            {
                "chunk_id": str(row["chunk_id"]),
                "text": row["text"],
                "cosine_similarity": cosine_similarity,
                "source_filename": row["source_filename"],
                "page_number": row["page_number"],
                "subject_id": str(row["subject_id"]) if row["subject_id"] else None,
                "module_id": str(row["module_id"]) if row["module_id"] else None,
                "topic_id": str(row["topic_id"]) if row["topic_id"] else None,
            }
        )

    # Results already sorted ascending by distance (= descending by similarity)
    # but we re-sort to be explicit.
    results.sort(key=lambda r: r["cosine_similarity"], reverse=True)
    return results
