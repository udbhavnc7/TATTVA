"""
SQLAlchemy ORM models for the Tattva Exam Engine.

All 13 tables are declared here, mapped exactly to the PostgreSQL schema
defined in the design document.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import TIMESTAMP as _TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

# Timezone-aware timestamp shorthand used throughout this module.
TIMESTAMPTZ = _TIMESTAMP(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Core taxonomy
# ---------------------------------------------------------------------------


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(r"code ~ '^[A-Za-z0-9]{4,10}$'", name="subjects_code_format"),
    )

    # relationships
    modules: Mapped[List["Module"]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(back_populates="subject")
    pyqs: Mapped[List["Pyq"]] = relationship(back_populates="subject")


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (UniqueConstraint("subject_id", "number", name="modules_subject_number_ux"),)

    # relationships
    subject: Mapped["Subject"] = relationship(back_populates="modules")
    topics: Mapped[List["Topic"]] = relationship(
        back_populates="module", cascade="all, delete-orphan"
    )


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # CHAR(64) stored as VARCHAR(64) in SQLAlchemy
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_updated: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )
    pending_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # relationships
    module: Mapped["Module"] = relationship(back_populates="topics")
    chunks: Mapped[List["Chunk"]] = relationship(back_populates="topic")
    notes: Mapped[List["Note"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    flashcards: Mapped[List["Flashcard"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    importance: Mapped[Optional["TopicImportance"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan", uselist=False
    )
    pyqs: Mapped[List["Pyq"]] = relationship(back_populates="topic")


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('manual', 'drive', 'classroom')",
            name="documents_source_type_ck",
        ),
        CheckConstraint(
            "status IN ('pending','parsing','classified','classification_failed','ready','error')",
            name="documents_status_ck",
        ),
    )

    # relationships
    subject: Mapped[Optional["Subject"]] = relationship(back_populates="documents")
    chunks: Mapped[List["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    note_versions: Mapped[List["NoteVersion"]] = relationship(
        back_populates="source_document"
    )
    classifications: Mapped[List["Classification"]] = relationship(
        back_populates="document"
    )


# ---------------------------------------------------------------------------
# Chunks (core retrieval unit)
# ---------------------------------------------------------------------------


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    topic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id"),
        nullable=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint("page_number >= 1", name="chunks_page_number_ck"),
        CheckConstraint("token_count >= 1", name="chunks_token_count_ck"),
        # IVFFlat and plain indexes are created in the migration script.
    )

    # relationships
    topic: Mapped[Optional["Topic"]] = relationship(back_populates="chunks")
    document: Mapped["Document"] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# Generated notes
# ---------------------------------------------------------------------------


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    depth: Mapped[str] = mapped_column(String(10), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )
    mermaid_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_cache_key: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "depth IN ('2mark', '6mark', '10mark')", name="notes_depth_ck"
        ),
        CheckConstraint(
            "confidence IN ('grounded', 'partial', 'needs_review')",
            name="notes_confidence_ck",
        ),
        # Composite index created in migration.
    )

    # relationships
    topic: Mapped["Topic"] = relationship(back_populates="notes")
    versions: Mapped[List["NoteVersion"]] = relationship(back_populates="note")
    validation_flags: Mapped[List["ValidationFlag"]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )
    flashcards: Mapped[List["Flashcard"]] = relationship(back_populates="note")


# ---------------------------------------------------------------------------
# Note version history (immutable — never delete rows)
# ---------------------------------------------------------------------------


class NoteVersion(Base):
    __tablename__ = "note_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notes.id"),
        nullable=False,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    # relationships
    note: Mapped["Note"] = relationship(back_populates="versions")
    source_document: Mapped[Optional["Document"]] = relationship(
        back_populates="note_versions"
    )


# ---------------------------------------------------------------------------
# Validation flags (from Confidence Validator)
# ---------------------------------------------------------------------------


class ValidationFlag(Base):
    __tablename__ = "validation_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notes.id"),
        nullable=False,
    )
    flagged_sentence: Mapped[str] = mapped_column(Text, nullable=False)
    flagged_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    # relationships
    note: Mapped["Note"] = relationship(back_populates="validation_flags")


# ---------------------------------------------------------------------------
# PYQ tables
# ---------------------------------------------------------------------------


class Pyq(Base):
    __tablename__ = "pyqs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    topic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id"),
        nullable=True,
    )
    marks: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    difficulty_note: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    secondary_topics: Mapped[Optional[list]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    is_unmatched: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint("year BETWEEN 2000 AND 2100", name="pyqs_year_ck"),
        CheckConstraint(
            "char_length(question_text) BETWEEN 10 AND 2000",
            name="pyqs_question_text_ck",
        ),
        CheckConstraint("marks BETWEEN 1 AND 100", name="pyqs_marks_ck"),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard') OR difficulty IS NULL",
            name="pyqs_difficulty_ck",
        ),
    )

    # relationships
    subject: Mapped["Subject"] = relationship(back_populates="pyqs")
    topic: Mapped[Optional["Topic"]] = relationship(back_populates="pyqs")


class TopicImportance(Base):
    __tablename__ = "topic_importance"

    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        primary_key=True,
    )
    frequency_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    difficulty_avg: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 2), nullable=True
    )
    last_recalculated: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMPTZ, nullable=True
    )

    # relationships
    topic: Mapped["Topic"] = relationship(back_populates="importance")


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    note_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notes.id"),
        nullable=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ease_factor: Mapped[float] = mapped_column(
        Numeric(4, 2), nullable=False, default=2.5
    )
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(answer) <= 300", name="flashcards_answer_len_ck"
        ),
        CheckConstraint(
            "ease_factor >= 1.3", name="flashcards_ease_factor_ck"
        ),
        # Indexes created in migration.
    )

    # relationships
    topic: Mapped["Topic"] = relationship(back_populates="flashcards")
    note: Mapped[Optional["Note"]] = relationship(back_populates="flashcards")


# ---------------------------------------------------------------------------
# Classification records
# ---------------------------------------------------------------------------


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        nullable=False,
    )
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    module_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_new_topic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    pending_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="classifications_confidence_ck",
        ),
    )

    # relationships
    document: Mapped["Document"] = relationship(back_populates="classifications")


# ---------------------------------------------------------------------------
# OAuth tokens (Drive integration)
# ---------------------------------------------------------------------------


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(30), nullable=False, default="google"
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, default=_now
    )

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="oauth_tokens_user_provider_ux"),
    )


# ---------------------------------------------------------------------------
# Explicit table-level indexes (mirrored from migration for ORM introspection)
# These are defined here so that `Base.metadata` is aware of them, even
# though they are also created via raw DDL in the Alembic migration.
# ---------------------------------------------------------------------------

Index("ix_chunks_embedding_ivfflat", Chunk.__table__.c.embedding, postgresql_using="ivfflat", postgresql_with={"lists": 100}, postgresql_ops={"embedding": "vector_cosine_ops"})  # noqa: E501
Index("ix_chunks_topic_id", Chunk.__table__.c.topic_id)
Index("ix_chunks_document_id", Chunk.__table__.c.document_id)
Index("ix_notes_topic_depth_version", Note.__table__.c.topic_id, Note.__table__.c.depth, Note.__table__.c.version)
Index("ix_flashcards_topic_id", Flashcard.__table__.c.topic_id)
Index("ix_flashcards_next_review_at", Flashcard.__table__.c.next_review_at)
