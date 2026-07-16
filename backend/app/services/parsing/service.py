"""
Parsing Service — Tasks 3.1, 3.2, 3.3, 3.4

Implements:
  - PyMuPDF-based text extraction per page (Task 3.1)
  - Tesseract OCR fallback for image-only pages (Task 3.2)
  - Sliding-window sentence-boundary chunk splitter (Task 3.3)
  - DB storage with atomic rollback on failure (Task 3.4)

All public functions are synchronous (CPU-bound PDF work); DB storage uses
the async SQLAlchemy session passed in by the caller.

Sentence splitting uses a simple regex `[.!?]+\\s` rather than NLTK to avoid
requiring NLTK data downloads during tests or in minimal environments.
"""

from __future__ import annotations

import io
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

import fitz  # PyMuPDF
import tiktoken
from PIL import Image
import pytesseract
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tokeniser (cl100k_base — same encoding used by GPT-4 / text-embedding-ada)
# ---------------------------------------------------------------------------
_ENCODING = tiktoken.get_encoding("cl100k_base")

# Chunk size limits (in tokens)
CHUNK_MIN_TOKENS = 400
CHUNK_MAX_TOKENS = 600

# Sentinel appended when a single sentence is hard-split
TRUNCATION_MARKER = "[truncated]"


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------

@dataclass
class ChunkData:
    """Lightweight DTO for a text chunk produced by the parser."""
    document_id: uuid.UUID
    page_number: int   # 1-indexed
    text: str
    token_count: int


# ---------------------------------------------------------------------------
# 3.1 — PyMuPDF text extraction
# ---------------------------------------------------------------------------

def extract_page_text(page: fitz.Page) -> str:
    """Extract all text from a PyMuPDF page object.

    Returns the plain text string for the page. Returns an empty string
    when the page carries no text layer (image-only pages).
    """
    # "text" mode returns a plain string; "blocks" / "dict" modes provide
    # richer structure but plain text is sufficient for chunking.
    return page.get_text("text")  # type: ignore[attr-defined]


def extract_page_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    """Extract structured blocks (headings, body, tables, figures) from a page.

    Each block is a dict with keys: type, text, bbox, page_number.
    This metadata is recorded per-segment as required by Requirement 3.1 / 3.3.
    """
    raw_blocks = page.get_text("blocks")  # list of (x0,y0,x1,y1,text,block_no,block_type)
    blocks: list[dict[str, Any]] = []
    for blk in raw_blocks:
        x0, y0, x1, y1, text, block_no, block_type = blk
        if block_type == 0:
            segment_type = "text"
        elif block_type == 1:
            segment_type = "figure"
        else:
            segment_type = "other"
        blocks.append(
            {
                "type": segment_type,
                "text": text,
                "bbox": (x0, y0, x1, y1),
                "block_number": block_no,
            }
        )
    return blocks


# ---------------------------------------------------------------------------
# 3.2 — Tesseract OCR fallback
# ---------------------------------------------------------------------------

def ocr_page(page: fitz.Page) -> str:
    """Run Tesseract OCR on a PyMuPDF page rendered at 150 DPI.

    Only called when ``extract_page_text`` yields zero characters for the page.
    Returns the OCR result as a plain string (may be empty if the image is
    blank or Tesseract cannot detect any characters).
    """
    # Render the page to a pixmap at 150 DPI for OCR
    matrix = fitz.Matrix(150 / 72, 150 / 72)
    pixmap = page.get_pixmap(matrix=matrix)  # type: ignore[attr-defined]

    # Convert to PIL Image for pytesseract
    img_bytes = pixmap.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    text: str = pytesseract.image_to_string(img)
    return text


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _count_tokens(text: str) -> int:
    """Return the cl100k_base token count for *text*."""
    return len(_ENCODING.encode(text))


def _encode(text: str) -> list[int]:
    return _ENCODING.encode(text)


def _decode(tokens: list[int]) -> str:
    return _ENCODING.decode(tokens)


# ---------------------------------------------------------------------------
# 3.3 — Sliding-window sentence-boundary chunk splitter
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split *text* into sentences using a simple regex splitter.

    Splits on one or more sentence-ending punctuation characters ([.!?])
    followed by whitespace, as specified in the design document.  This
    approach requires no external NLTK data downloads, keeping the service
    lightweight and test-friendly.
    """
    # Split at sentence boundaries: one-or-more of [.!?] followed by whitespace.
    # re.split keeps the delimiter attached to the preceding token via a
    # lookbehind so sentences end with their punctuation.
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter out empty / whitespace-only fragments
    return [s for s in parts if s.strip()]


def split_into_chunks(
    text: str,
    document_id: uuid.UUID,
    page_number: int,
) -> list[ChunkData]:
    """Split *text* into token-bounded chunks using sentence-boundary awareness.

    Algorithm (Requirement 3.3 / Design §B):
    1. Tokenise *text* into sentences.
    2. Accumulate sentences until the next sentence would push the current
       chunk past ``CHUNK_MAX_TOKENS`` (600).
    3. If a single sentence is > 600 tokens, hard-split at token 600 and
       append ``[truncated]`` to the first portion; the remainder starts the
       next chunk.
    4. After all sentences are consumed, if the final (last) chunk has fewer
       than ``CHUNK_MIN_TOKENS`` (400) tokens *and* there is a preceding chunk
       to merge into, merge it with the previous chunk.

    Each returned ``ChunkData`` carries document_id and page_number verbatim.
    """
    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[ChunkData] = []
    current_tokens: list[int] = []

    def _flush(token_list: list[int]) -> None:
        if token_list:
            chunk_text = _decode(token_list)
            # Re-count tokens from the decoded text to avoid BPE boundary mismatch
            actual_token_count = _count_tokens(chunk_text)
            chunks.append(
                ChunkData(
                    document_id=document_id,
                    page_number=page_number,
                    text=chunk_text,
                    token_count=actual_token_count,
                )
            )

    truncation_tokens = _encode(" " + TRUNCATION_MARKER)
    _trunc_len = len(truncation_tokens)

    for sentence in sentences:
        sentence_tokens = _encode(sentence)

        # Case: single sentence exceeds max — hard-split
        if len(sentence_tokens) > CHUNK_MAX_TOKENS:
            # First, flush whatever we've accumulated so far
            _flush(current_tokens)
            current_tokens = []

            # Hard-split the long sentence in CHUNK_MAX_TOKENS-token slabs
            offset = 0
            while offset < len(sentence_tokens):
                remaining = sentence_tokens[offset:]
                if len(remaining) <= CHUNK_MAX_TOKENS:
                    # Last slab — carry it forward into current_tokens so
                    # it can either be flushed normally or merged with the
                    # next sentence instead of sitting as a tiny isolated chunk.
                    current_tokens = list(remaining)
                    offset += len(remaining)
                else:
                    # More slabs follow — append truncation marker, keep within max
                    available = CHUNK_MAX_TOKENS - _trunc_len
                    slab = sentence_tokens[offset: offset + available] + truncation_tokens
                    _flush(slab)
                    offset += available
            continue

        # Would adding this sentence exceed the max?
        if len(current_tokens) + len(sentence_tokens) > CHUNK_MAX_TOKENS:
            _flush(current_tokens)
            current_tokens = list(sentence_tokens)
        else:
            current_tokens.extend(sentence_tokens)

    # Flush any remaining tokens as the final chunk
    _flush(current_tokens)

    # Merge final chunk into previous if it is below the minimum threshold
    # BUT only when merging would not push the resulting chunk beyond the max.
    if len(chunks) >= 2 and chunks[-1].token_count < CHUNK_MIN_TOKENS:
        prev = chunks[-2]
        last = chunks[-1]
        merged_text = prev.text + " " + last.text
        merged_tokens = _count_tokens(merged_text)
        # Guard: do not merge if it would violate the upper bound
        if merged_tokens <= CHUNK_MAX_TOKENS:
            chunks[-2] = ChunkData(
                document_id=document_id,
                page_number=page_number,
                text=merged_text,
                token_count=merged_tokens,
            )
            chunks.pop()

    return chunks


# ---------------------------------------------------------------------------
# Orchestrator — 3.1 + 3.2 + 3.3 combined
# ---------------------------------------------------------------------------

def parse_document(
    document_id: uuid.UUID,
    file_bytes: bytes,
) -> list[ChunkData]:
    """Parse a PDF from raw bytes and return all chunks with page attribution.

    Per-page behaviour:
    - Try PyMuPDF text extraction first.
    - If a page yields zero characters, fall back to Tesseract OCR.
    - If a page is still empty after OCR, log an unprocessable-page entry and
      continue to the next page (Requirement 3.5).
    """
    all_chunks: list[ChunkData] = []

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.error(
            "Failed to open PDF for document_id=%s: %s", document_id, exc
        )
        raise

    for page_index in range(len(doc)):
        page_number = page_index + 1  # 1-indexed
        page = doc[page_index]

        # --- 3.1 PyMuPDF extraction ---
        text = extract_page_text(page)

        # --- 3.2 OCR fallback ---
        if not text.strip():
            logger.debug(
                "Page %d of document %s: no PyMuPDF text, trying OCR",
                page_number,
                document_id,
            )
            try:
                text = ocr_page(page)
            except Exception as exc:
                logger.warning(
                    "OCR failed on page %d of document %s: %s",
                    page_number,
                    document_id,
                    exc,
                )
                text = ""

        # --- 3.2 Unprocessable page logging ---
        if not text.strip():
            logger.warning(
                "Unprocessable page: %s",
                {
                    "document_id": str(document_id),
                    "page_number": page_number,
                    "reason": "no_text_extracted",
                },
            )
            # Do NOT raise — continue to the next page per Requirement 3.5
            continue

        # --- 3.3 Chunk splitting ---
        page_chunks = split_into_chunks(text, document_id, page_number)
        all_chunks.extend(page_chunks)

    doc.close()
    return all_chunks


# ---------------------------------------------------------------------------
# 3.4 — Knowledge Store write with rollback on failure
# ---------------------------------------------------------------------------

async def store_chunks(
    session: AsyncSession,
    chunks: list[ChunkData],
) -> None:
    """Persist *chunks* to the ``chunks`` table inside the provided session.

    If any single ``session.add`` / ``session.flush`` raises an Exception,
    the session is rolled back and a descriptive RuntimeError is raised that
    identifies the document_id (Requirement 3.7).

    The caller is responsible for providing an open (not yet committed) session.
    After a successful call the caller should commit the session.
    """
    if not chunks:
        return

    document_id = chunks[0].document_id

    try:
        for chunk_data in chunks:
            orm_chunk = Chunk(
                document_id=chunk_data.document_id,
                page_number=chunk_data.page_number,
                text=chunk_data.text,
                token_count=chunk_data.token_count,
            )
            session.add(orm_chunk)

        # Flush to surface any constraint violations before committing
        await session.flush()

    except Exception as exc:
        await session.rollback()
        raise RuntimeError(
            f"Knowledge Store write failed for document_id={document_id}: {exc}"
        ) from exc
