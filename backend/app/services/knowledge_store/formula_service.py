"""
Formula Scanner Service — business logic layer.

Responsibilities:
  - Scan all chunks for a subject and extract formulas/equations/algorithm pseudocode
    using regex/heuristic extraction (NO LLM).
  - Flag incomplete formulas (containing '...' or cut-off mid-expression).
  - Render results as a Markdown table.
  - Fall back to a numbered list if Markdown table rendering fails.
  - DB queries: chunks → documents → topics → modules → subjects join.

Extraction rules (regex/heuristic, case-insensitive):
  1. Equations: patterns like `x = ...`, `F = ma`, LaTeX-style `\\frac{}{}`,
     `^`, `_` subscript/superscript indicators.
  2. Algorithm pseudocode: lines starting with keywords: if, for, while,
     return, function, def, algorithm, procedure.
  3. Formulas: mathematical expressions involving +, -, *, /, = with variables.

Each extracted item: { formula_or_algorithm, variables, source }
  - variables: unique single-letter identifiers (A-Z, a-z) from the expression.
  - source: "filename.pdf, p.N" from the chunk's document.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------

# LaTeX-style expressions
_LATEX_RE = re.compile(
    r"\\(?:frac|sqrt|sum|int|prod|lim|infty|alpha|beta|gamma|delta|theta|lambda|mu|sigma|omega)"
    r"|\\\{|\\\}|\^[{]?[A-Za-z0-9]+[}]?|_[{]?[A-Za-z0-9]+[}]?",
    re.IGNORECASE,
)

# Equation pattern: variable(s) = expression  (e.g. F = ma, E = mc^2, x = a+b)
_EQUATION_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*\s*=\s*[A-Za-z0-9_\+\-\*\/\^\(\)\.\s\\{},]+",
    re.IGNORECASE,
)

# Pure math expression: contains operators and at least one letter variable
_MATH_EXPR_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_]*\s*[\+\-\*\/]\s*[A-Za-z0-9_\+\-\*\/\^\(\)\.\s]+",
    re.IGNORECASE,
)

# Algorithm / pseudocode line keywords
_ALGO_KEYWORDS_RE = re.compile(
    r"^\s*(if|for|while|return|function|def|algorithm|procedure)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Incomplete formula indicator
_INCOMPLETE_RE = re.compile(r"\.\.\.|…")

# Single-letter variable extractor (A-Z, a-z) — ignores multi-char words
_VAR_RE = re.compile(r"\b([A-Za-z])\b")


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def _extract_variables(expression: str) -> str:
    """
    Extract unique single-letter identifiers from *expression*.

    Returns a comma-separated sorted string, e.g. "F, a, m".
    Returns empty string if none found.
    """
    # Strip LaTeX commands before extracting variables so that backslash
    # sequences are not mistakenly counted.
    cleaned = re.sub(r"\\[A-Za-z]+", "", expression)
    vars_found = sorted(set(_VAR_RE.findall(cleaned)))
    return ", ".join(vars_found) if vars_found else ""


def _is_incomplete(expr: str) -> bool:
    """Return True if the expression looks incomplete."""
    return bool(_INCOMPLETE_RE.search(expr))


def _flag_incomplete(expr: str) -> str:
    """Append [incomplete in source] marker if needed."""
    if _is_incomplete(expr):
        return expr.strip() + " [incomplete in source]"
    return expr.strip()


def _extract_formulas_from_text(
    text_content: str,
    source: str,
) -> list[dict[str, str]]:
    """
    Extract all formulas/equations/algorithms from a single chunk's text.

    Returns a list of dicts:
      { "formula_or_algorithm": str, "variables": str, "source": str }
    """
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(expr: str) -> None:
        flagged = _flag_incomplete(expr)
        if flagged and flagged not in seen:
            seen.add(flagged)
            results.append(
                {
                    "formula_or_algorithm": flagged,
                    "variables": _extract_variables(expr),
                    "source": source,
                }
            )

    # 1. Equation matches (highest priority — most formula-like)
    for m in _EQUATION_RE.finditer(text_content):
        _add(m.group(0))

    # 2. LaTeX-containing lines
    for line in text_content.splitlines():
        if _LATEX_RE.search(line):
            stripped = line.strip()
            if stripped:
                _add(stripped)

    # 3. Algorithm pseudocode lines
    for m in _ALGO_KEYWORDS_RE.finditer(text_content):
        # Grab the full line from the match position
        start = m.start()
        end = text_content.find("\n", start)
        line = text_content[start: end if end != -1 else len(text_content)].strip()
        if line:
            _add(line)

    # 4. Pure math expressions (catch-all — only if not already captured)
    for m in _MATH_EXPR_RE.finditer(text_content):
        _add(m.group(0))

    return results


# ---------------------------------------------------------------------------
# Markdown table rendering
# ---------------------------------------------------------------------------

_TABLE_HEADER = (
    "| Formula/Algorithm | Variables | Source |\n"
    "|---|---|---|\n"
)


def render_markdown_table(formulas: list[dict[str, str]]) -> str:
    """
    Render *formulas* as a Markdown table.

    Raises ValueError if *formulas* is empty (caller should use fallback).
    Raises RuntimeError on any unexpected rendering failure.
    """
    if not formulas:
        raise ValueError("No formulas to render.")

    rows = []
    for item in formulas:
        fa = item.get("formula_or_algorithm", "").replace("|", "\\|")
        v = item.get("variables", "").replace("|", "\\|")
        s = item.get("source", "").replace("|", "\\|")
        rows.append(f"| {fa} | {v} | {s} |")

    return _TABLE_HEADER + "\n".join(rows)


def render_fallback_list(formulas: list[dict[str, str]]) -> str:
    """
    Render *formulas* as a numbered list (fallback).

    Format:
      1. Formula/Algorithm: <expr> | Variables: <vars> | Source: <src>
    """
    lines = []
    for i, item in enumerate(formulas, start=1):
        fa = item.get("formula_or_algorithm", "")
        v = item.get("variables", "")
        s = item.get("source", "")
        lines.append(f"{i}. Formula/Algorithm: {fa} | Variables: {v} | Source: {s}")
    return "\n".join(lines)


def build_rendered_table(formulas: list[dict[str, str]]) -> str:
    """
    Attempt to render a Markdown table; fall back to numbered list on error.
    """
    try:
        return render_markdown_table(formulas)
    except Exception:  # noqa: BLE001
        return render_fallback_list(formulas)


# ---------------------------------------------------------------------------
# Database query — fetch chunks for a subject
# ---------------------------------------------------------------------------

_CHUNKS_FOR_SUBJECT_SQL = text(
    """
    SELECT
        c.text        AS chunk_text,
        d.filename    AS filename,
        c.page_number AS page_number
    FROM chunks c
    JOIN documents d  ON d.id = c.document_id
    JOIN topics    t  ON t.id = c.topic_id
    JOIN modules   mo ON mo.id = t.module_id
    WHERE mo.subject_id = :subject_id
    ORDER BY d.filename, c.page_number
    """
)


async def get_chunks_for_subject(
    session: AsyncSession,
    subject_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """
    Return all chunks (text, filename, page_number) associated with *subject_id*.

    Traverses: chunks → topics → modules → subjects.
    Returns an empty list if no chunks are found.
    """
    rows = await session.execute(
        _CHUNKS_FOR_SUBJECT_SQL, {"subject_id": str(subject_id)}
    )
    return [
        {
            "chunk_text": r[0],
            "filename": r[1],
            "page_number": r[2],
        }
        for r in rows.fetchall()
    ]


# ---------------------------------------------------------------------------
# High-level scan function
# ---------------------------------------------------------------------------


async def scan_formulas(
    session: AsyncSession,
    subject_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Scan all chunks for *subject_id*, extract formulas/algorithms, and render
    the Markdown table.

    Returns:
      {
        "subject_id": str,
        "formulas": list[dict],
        "rendered_table": str,
      }
    """
    chunks = await get_chunks_for_subject(session, subject_id)

    all_formulas: list[dict[str, str]] = []
    for chunk in chunks:
        source = f"{chunk['filename']}, p.{chunk['page_number']}"
        extracted = _extract_formulas_from_text(chunk["chunk_text"], source)
        all_formulas.extend(extracted)

    rendered = build_rendered_table(all_formulas)

    return {
        "subject_id": str(subject_id),
        "formulas": all_formulas,
        "rendered_table": rendered,
    }
