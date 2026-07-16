"""
Incremental Diff Pipeline — Task 6 (Tattva Exam Engine).

Public API
----------
compute_topic_hash(text: str) -> str
    Returns a 64-character SHA-256 hex digest of the normalized topic text.
    Normalization: NFC Unicode → strip leading/trailing whitespace →
    collapse internal whitespace runs to a single space.

check_hash_changed(topic, new_hash: str) -> bool
    Returns True when the topic needs downstream processing:
      - topic.content_hash is None  → first ingestion (always process)
      - topic.content_hash != new_hash → content changed (process)
      - topic.content_hash == new_hash → unchanged (skip)
    When force_regenerate is True the caller passes None for topic so
    this function isn't reached; see router integration notes.

apply_version_bump(session, topic, new_hash, note, source_document_id) -> NoteVersion
    Atomically:
      1. Increments topic.version by 1
      2. Stores new_hash in topic.content_hash
      3. Writes a NoteVersion record capturing the current note state
    If the NoteVersion flush fails the exception propagates and the
    caller's session is expected to roll back the entire transaction
    (guaranteed by get_db context-manager in session.py).

    Returns the newly created NoteVersion instance.

Never-delete guarantee (Task 6.5)
-----------------------------------
NoteVersion rows must never be deleted.  This is enforced at the service
layer: apply_version_bump only adds rows, never deletes them, and the
minimum-10-records invariant is validated by count_topic_versions().
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.db.models import NoteVersion, Note, Topic


# ---------------------------------------------------------------------------
# 6.1 — Per-topic SHA-256 hash from normalized text
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Normalize topic text before hashing.

    Steps (in order — order matters):
      1. Unicode NFC normalization
      2. Strip leading/trailing whitespace
      3. Collapse internal whitespace sequences to a single space
    """
    nfc = unicodedata.normalize("NFC", text)
    stripped = nfc.strip()
    collapsed = re.sub(r"\s+", " ", stripped)
    return collapsed


def compute_topic_hash(text: str) -> str:
    """
    Return a 64-character lowercase SHA-256 hex digest of the normalized
    topic text.

    >>> h = compute_topic_hash("  hello   world  ")
    >>> h == compute_topic_hash("hello world")
    True
    >>> len(h)
    64
    """
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 6.2 — Hash comparison logic
# ---------------------------------------------------------------------------

def check_hash_changed(topic: Topic, new_hash: str) -> bool:
    """
    Return True if the full pipeline should run for *topic*.

    Rules:
    - stored hash is None  → first ingestion → True (run pipeline)
    - stored hash == new_hash → unchanged   → False (skip downstream)
    - stored hash != new_hash → changed     → True (run pipeline)

    The force_regenerate flag is handled by the caller *before* calling
    this function — if force_regenerate is True the caller skips this
    check entirely and runs the pipeline unconditionally.
    """
    if topic.content_hash is None:
        return True  # First ingestion — no stored hash yet
    return topic.content_hash != new_hash


# ---------------------------------------------------------------------------
# 6.3 — On hash change: version bump + note_versions record + rollback guard
# ---------------------------------------------------------------------------

async def apply_version_bump(
    session: AsyncSession,
    topic: Topic,
    new_hash: str,
    note: Note,
    source_document_id: Optional[uuid.UUID] = None,
) -> NoteVersion:
    """
    Atomically record a content-hash change for *topic*.

    Steps:
      1. Increment topic.version by 1.
      2. Set topic.content_hash = new_hash.
      3. Create and flush a NoteVersion record.

    If the NoteVersion flush raises, the exception propagates.  The
    enclosing ``get_db`` async context manager will call
    ``session.rollback()`` before re-raising, so no partial state is
    persisted.

    Parameters
    ----------
    session:
        Active SQLAlchemy AsyncSession (provided by get_db).
    topic:
        The Topic ORM instance whose version should be bumped.
    new_hash:
        The new 64-character SHA-256 hex digest for the topic text.
    note:
        The current Note for this topic (used to populate the history
        record).
    source_document_id:
        Optional UUID of the Document that caused this regeneration.

    Returns
    -------
    NoteVersion
        The newly created (and flushed) history record.
    """
    # Step 1 & 2 — update topic fields
    topic.version += 1
    topic.content_hash = new_hash
    topic.last_updated = datetime.now(timezone.utc)

    # Step 3 — write the immutable history record
    nv = NoteVersion(
        note_id=note.id,
        topic_id=topic.id,
        version=topic.version,  # already incremented above
        content_md=note.content_md,
        confidence=note.confidence,
        generated_at=note.generated_at,
        source_document_id=source_document_id,
    )
    session.add(nv)

    # Flush so any DB constraint error surfaces here, inside the
    # transaction, before the caller can observe the version bump.
    # If this raises, the entire transaction is rolled back by get_db.
    await session.flush()

    return nv


# ---------------------------------------------------------------------------
# 6.5 — Version history enforcement (read-only helper)
# ---------------------------------------------------------------------------

async def count_topic_versions(session: AsyncSession, topic_id: uuid.UUID) -> int:
    """
    Return the number of NoteVersion rows for *topic_id*.

    The design requires ≥ 10 historical records per topic once at least
    10 regenerations have occurred.  This function is used by callers and
    tests to verify that the never-delete guarantee holds.
    """
    result = await session.execute(
        select(func.count()).where(NoteVersion.topic_id == topic_id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# 6.4 — force_regenerate flag (documented here, wired in the router)
# ---------------------------------------------------------------------------
# The force_regenerate flag is a boolean parameter on POST /generate-notes.
# When True the caller skips check_hash_changed() and calls the full
# pipeline unconditionally — equivalent to treating every invocation as a
# first ingestion.  The flag does NOT bypass apply_version_bump; a new
# NoteVersion record is still written when force_regenerate is True and
# generation succeeds.
#
# Router integration (to be added in Task 7):
#
#   @router.post("/generate-notes")
#   async def generate_notes(
#       topic_id: UUID,
#       depth: str,
#       force_regenerate: bool = False,
#       ...
#   ):
#       ...
#       if not force_regenerate and not check_hash_changed(topic, new_hash):
#           return cached_response       # skip — Task 6.2
#       ...                              # run full pipeline
#       await apply_version_bump(...)    # Task 6.3
