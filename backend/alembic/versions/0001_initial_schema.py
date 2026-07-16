"""Initial schema — all 13 tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

Creates the complete Tattva Exam Engine schema:
  subjects, modules, topics,
  documents, chunks,
  notes, note_versions, validation_flags,
  pyqs, topic_importance,
  flashcards,
  classifications,
  oauth_tokens

Also enables the pgvector extension required for the chunks.embedding column.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0. Extensions
    # ------------------------------------------------------------------
    # pgvector must exist before we create the chunks table.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # 1. subjects
    # ------------------------------------------------------------------
    op.create_table(
        "subjects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("code", name="subjects_code_ux"),
        sa.CheckConstraint(
            r"code ~ '^[A-Za-z0-9]{4,10}$'", name="subjects_code_format"
        ),
    )

    # ------------------------------------------------------------------
    # 2. modules
    # ------------------------------------------------------------------
    op.create_table(
        "modules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.UniqueConstraint("subject_id", "number", name="modules_subject_number_ux"),
    )

    # ------------------------------------------------------------------
    # 3. topics
    # ------------------------------------------------------------------
    op.create_table(
        "topics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "module_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "last_updated",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "pending_review",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ------------------------------------------------------------------
    # 4. documents
    # ------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subjects.id"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.CheckConstraint(
            "source_type IN ('manual', 'drive', 'classroom')",
            name="documents_source_type_ck",
        ),
        sa.CheckConstraint(
            "status IN ('pending','parsing','classified','classification_failed','ready','error')",
            name="documents_status_ck",
        ),
    )

    # ------------------------------------------------------------------
    # 5. chunks  (requires pgvector extension)
    # ------------------------------------------------------------------
    # We use execute() for the vector column because SQLAlchemy core does
    # not natively emit USING ivfflat syntax via Column objects.
    op.create_table(
        "chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("embedding", sa.Text, nullable=True),  # placeholder; altered below
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("page_number >= 1", name="chunks_page_number_ck"),
        sa.CheckConstraint("token_count >= 1", name="chunks_token_count_ck"),
    )

    # Swap placeholder TEXT column for the real vector(1536) type.
    op.execute("ALTER TABLE chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1536)")

    # IVFFlat index for cosine similarity search.
    op.execute(
        "CREATE INDEX ix_chunks_embedding_ivfflat "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
    op.create_index("ix_chunks_topic_id", "chunks", ["topic_id"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])

    # ------------------------------------------------------------------
    # 6. notes
    # ------------------------------------------------------------------
    op.create_table(
        "notes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("depth", sa.String(10), nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column(
            "generated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("mermaid_code", sa.Text, nullable=True),
        sa.Column("audio_cache_key", sa.String(500), nullable=True),
        sa.CheckConstraint(
            "depth IN ('2mark', '6mark', '10mark')", name="notes_depth_ck"
        ),
        sa.CheckConstraint(
            "confidence IN ('grounded', 'partial', 'needs_review')",
            name="notes_confidence_ck",
        ),
    )
    op.create_index(
        "ix_notes_topic_depth_version",
        "notes",
        ["topic_id", "depth", "version"],
    )

    # ------------------------------------------------------------------
    # 7. note_versions
    # ------------------------------------------------------------------
    op.create_table(
        "note_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id"),
            nullable=False,
        ),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("content_md", sa.Text, nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column(
            "generated_at", sa.TIMESTAMP(timezone=True), nullable=False
        ),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ------------------------------------------------------------------
    # 8. validation_flags
    # ------------------------------------------------------------------
    op.create_table(
        "validation_flags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id"),
            nullable=False,
        ),
        sa.Column("flagged_sentence", sa.Text, nullable=False),
        sa.Column(
            "flagged_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ------------------------------------------------------------------
    # 9. pyqs
    # ------------------------------------------------------------------
    op.create_table(
        "pyqs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subjects.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id"),
            nullable=True,
        ),
        sa.Column("marks", sa.Integer, nullable=False),
        sa.Column("difficulty", sa.String(10), nullable=True),
        sa.Column("difficulty_note", sa.String(200), nullable=True),
        sa.Column(
            "secondary_topics",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
        sa.Column(
            "is_unmatched", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("year BETWEEN 2000 AND 2100", name="pyqs_year_ck"),
        sa.CheckConstraint(
            "char_length(question_text) BETWEEN 10 AND 2000",
            name="pyqs_question_text_ck",
        ),
        sa.CheckConstraint("marks BETWEEN 1 AND 100", name="pyqs_marks_ck"),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard') OR difficulty IS NULL",
            name="pyqs_difficulty_ck",
        ),
    )

    # ------------------------------------------------------------------
    # 10. topic_importance
    # ------------------------------------------------------------------
    op.create_table(
        "topic_importance",
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "frequency_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("difficulty_avg", sa.Numeric(4, 2), nullable=True),
        sa.Column("last_recalculated", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # 11. flashcards
    # ------------------------------------------------------------------
    op.create_table(
        "flashcards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id"),
            nullable=True,
        ),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("source", sa.String(500), nullable=True),
        sa.Column(
            "ease_factor",
            sa.Numeric(4, 2),
            nullable=False,
            server_default="2.5",
        ),
        sa.Column(
            "interval_days", sa.Integer, nullable=False, server_default="1"
        ),
        sa.Column(
            "repetitions", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "next_review_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "char_length(answer) <= 300", name="flashcards_answer_len_ck"
        ),
        sa.CheckConstraint(
            "ease_factor >= 1.3", name="flashcards_ease_factor_ck"
        ),
    )
    op.create_index("ix_flashcards_topic_id", "flashcards", ["topic_id"])
    op.create_index("ix_flashcards_next_review_at", "flashcards", ["next_review_at"])

    # ------------------------------------------------------------------
    # 12. classifications
    # ------------------------------------------------------------------
    op.create_table(
        "classifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("module_number", sa.Integer, nullable=True),
        sa.Column("topic", sa.String(255), nullable=True),
        sa.Column(
            "is_new_topic", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("confidence", sa.String(10), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column(
            "pending_review", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="classifications_confidence_ck",
        ),
    )

    # ------------------------------------------------------------------
    # 13. oauth_tokens
    # ------------------------------------------------------------------
    op.create_table(
        "oauth_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider", sa.String(30), nullable=False, server_default="google"
        ),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=False),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "user_id", "provider", name="oauth_tokens_user_provider_ux"
        ),
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_table("oauth_tokens")
    op.drop_table("classifications")
    op.drop_index("ix_flashcards_next_review_at", table_name="flashcards")
    op.drop_index("ix_flashcards_topic_id", table_name="flashcards")
    op.drop_table("flashcards")
    op.drop_table("topic_importance")
    op.drop_table("pyqs")
    op.drop_table("validation_flags")
    op.drop_table("note_versions")
    op.drop_index("ix_notes_topic_depth_version", table_name="notes")
    op.drop_table("notes")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_index("ix_chunks_topic_id", table_name="chunks")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_ivfflat")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("topics")
    op.drop_table("modules")
    op.drop_table("subjects")
    op.execute("DROP EXTENSION IF EXISTS vector")
