"""
Unit tests for the Formula Scanner (Task 13).

Covers:
  - Regex extraction finds LaTeX-style formula in text
  - Algorithm pseudocode detected by keyword
  - Incomplete formula flagged with '[incomplete in source]'
  - Markdown table rendered correctly
  - Fallback to numbered list when table rendering raises
  - GET /formulas/{subject_id}/export returns Content-Disposition attachment header
  - POST /formulas/{subject_id}/scan returns status=completed
  - GET /formulas/{subject_id} returns subject_id, formulas list, rendered_table
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.knowledge_store.formula_service import (
    _extract_formulas_from_text,
    _extract_variables,
    _flag_incomplete,
    _is_incomplete,
    build_rendered_table,
    render_fallback_list,
    render_markdown_table,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _make_db_mock_with_chunks(chunks: list[dict]) -> tuple[AsyncMock, AsyncMock]:
    """
    Build a (mock_session, mock_cm) pair that returns *chunks* when
    session.execute() is called.

    Each chunk dict must have keys: chunk_text, filename, page_number.
    """
    # Build fake Row objects that support positional indexing
    fake_rows = []
    for c in chunks:
        row = (c["chunk_text"], c["filename"], c["page_number"])
        fake_rows.append(row)

    execute_result = MagicMock()
    execute_result.fetchall = MagicMock(return_value=fake_rows)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=execute_result)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_cm


def _make_empty_db_mock() -> tuple[AsyncMock, AsyncMock]:
    return _make_db_mock_with_chunks([])


# ===========================================================================
# Service-layer unit tests
# ===========================================================================


class TestExtractVariables:
    """Tests for _extract_variables helper."""

    def test_extracts_single_letter_vars_from_equation(self) -> None:
        expr = "F = m * a"
        vars_ = _extract_variables(expr)
        assert "F" in vars_
        assert "m" in vars_
        assert "a" in vars_

    def test_ignores_multi_letter_words(self) -> None:
        expr = "force = mass * acceleration"
        vars_ = _extract_variables(expr)
        # multi-letter words should not appear as single-letter variables
        assert "force" not in vars_
        assert "mass" not in vars_

    def test_returns_sorted_unique_vars(self) -> None:
        expr = "a + b + a + c"
        vars_ = _extract_variables(expr)
        parts = [v.strip() for v in vars_.split(",")]
        assert parts == sorted(set(parts))

    def test_empty_expression_returns_empty_string(self) -> None:
        assert _extract_variables("") == ""


class TestIsIncomplete:
    """Tests for _is_incomplete and _flag_incomplete helpers."""

    def test_ellipsis_detected_as_incomplete(self) -> None:
        assert _is_incomplete("F = m * ...") is True

    def test_unicode_ellipsis_detected(self) -> None:
        assert _is_incomplete("x = a + b + …") is True

    def test_complete_expression_not_flagged(self) -> None:
        assert _is_incomplete("F = m * a") is False

    def test_flag_incomplete_appends_marker(self) -> None:
        result = _flag_incomplete("F = m * ...")
        assert result.endswith("[incomplete in source]")

    def test_flag_complete_no_marker(self) -> None:
        result = _flag_incomplete("F = m * a")
        assert "[incomplete in source]" not in result


class TestExtractFormulasFromText:
    """Tests for the core extraction function."""

    def test_latex_frac_formula_extracted(self) -> None:
        """Regex extraction finds LaTeX-style formula in text."""
        text_content = r"The velocity is given by v = \frac{d}{t} where d is distance."
        results = _extract_formulas_from_text(text_content, "physics.pdf, p.5")
        formulas = [r["formula_or_algorithm"] for r in results]
        # At minimum, the LaTeX line or the equation should be captured
        assert any("frac" in f or "=" in f for f in formulas), (
            f"Expected LaTeX formula in {formulas}"
        )

    def test_algorithm_pseudocode_detected_by_if_keyword(self) -> None:
        """Algorithm pseudocode detected by 'if' keyword."""
        text_content = "if x > 0 then return x"
        results = _extract_formulas_from_text(text_content, "algo.pdf, p.1")
        formulas = [r["formula_or_algorithm"] for r in results]
        assert any("if" in f.lower() for f in formulas), (
            f"Expected 'if' keyword line in {formulas}"
        )

    def test_algorithm_pseudocode_detected_by_for_keyword(self) -> None:
        """Algorithm pseudocode detected by 'for' keyword."""
        text_content = "for i = 1 to n do\n    sum = sum + i\nend"
        results = _extract_formulas_from_text(text_content, "algo.pdf, p.2")
        formulas = [r["formula_or_algorithm"] for r in results]
        assert any("for" in f.lower() for f in formulas), (
            f"Expected 'for' keyword line in {formulas}"
        )

    def test_algorithm_pseudocode_detected_by_while_keyword(self) -> None:
        """'while' keyword triggers algorithm extraction."""
        text_content = "while n > 0:\n    n = n - 1"
        results = _extract_formulas_from_text(text_content, "algo.pdf, p.3")
        formulas = [r["formula_or_algorithm"] for r in results]
        assert any("while" in f.lower() for f in formulas)

    def test_algorithm_pseudocode_detected_by_return_keyword(self) -> None:
        """'return' keyword triggers algorithm extraction."""
        text_content = "return x * y"
        results = _extract_formulas_from_text(text_content, "algo.pdf, p.4")
        formulas = [r["formula_or_algorithm"] for r in results]
        assert any("return" in f.lower() for f in formulas)

    def test_algorithm_pseudocode_detected_by_function_keyword(self) -> None:
        """'function' keyword triggers algorithm extraction."""
        text_content = "function factorial(n) { return n * factorial(n-1) }"
        results = _extract_formulas_from_text(text_content, "algo.pdf, p.5")
        formulas = [r["formula_or_algorithm"] for r in results]
        assert any("function" in f.lower() for f in formulas)

    def test_incomplete_formula_flagged(self) -> None:
        """Incomplete formula (with '...') is flagged with [incomplete in source]."""
        text_content = "The equation is E = mc^2 + ..."
        results = _extract_formulas_from_text(text_content, "physics.pdf, p.10")
        flagged = [r for r in results if "[incomplete in source]" in r["formula_or_algorithm"]]
        assert len(flagged) >= 1, (
            f"Expected at least one incomplete formula; got {results}"
        )

    def test_source_field_preserved(self) -> None:
        """Each extracted item carries the correct source string."""
        text_content = "F = m * a"
        source = "mechanics.pdf, p.3"
        results = _extract_formulas_from_text(text_content, source)
        assert all(r["source"] == source for r in results)

    def test_no_formulas_in_plain_text(self) -> None:
        """Plain prose without math produces no extractions."""
        text_content = "The quick brown fox jumps over the lazy dog."
        results = _extract_formulas_from_text(text_content, "prose.pdf, p.1")
        # No equations, no algorithms, no math
        assert results == []

    def test_deduplication(self) -> None:
        """Duplicate formulas in the same chunk are only extracted once."""
        text_content = "F = ma\nF = ma\nF = ma"
        results = _extract_formulas_from_text(text_content, "phys.pdf, p.1")
        formulas = [r["formula_or_algorithm"] for r in results]
        assert len(formulas) == len(set(formulas))

    def test_equation_variables_extracted_correctly(self) -> None:
        """Variables in F = m * a are F, a, m."""
        text_content = "F = m * a"
        results = _extract_formulas_from_text(text_content, "phys.pdf, p.1")
        assert results
        vars_ = results[0]["variables"]
        for var in ["F", "m", "a"]:
            assert var in vars_, f"Expected '{var}' in variables '{vars_}'"


class TestRenderMarkdownTable:
    """Tests for render_markdown_table."""

    def test_markdown_table_rendered_correctly(self) -> None:
        """Markdown table rendered correctly with header and data rows."""
        formulas = [
            {
                "formula_or_algorithm": "F = ma",
                "variables": "F, a, m",
                "source": "physics.pdf, p.12",
            }
        ]
        table = render_markdown_table(formulas)
        assert "| Formula/Algorithm | Variables | Source |" in table
        assert "|---|---|---|" in table
        assert "F = ma" in table
        assert "F, a, m" in table
        assert "physics.pdf, p.12" in table

    def test_markdown_table_multiple_rows(self) -> None:
        """Multiple formulas produce multiple rows in table."""
        formulas = [
            {"formula_or_algorithm": "E = mc^2", "variables": "E, c, m", "source": "phys.pdf, p.1"},
            {"formula_or_algorithm": "F = ma", "variables": "F, a, m", "source": "phys.pdf, p.2"},
        ]
        table = render_markdown_table(formulas)
        assert "E = mc^2" in table
        assert "F = ma" in table

    def test_render_raises_on_empty_list(self) -> None:
        """render_markdown_table raises ValueError for empty input."""
        with pytest.raises((ValueError, Exception)):
            render_markdown_table([])


class TestRenderFallbackList:
    """Tests for render_fallback_list."""

    def test_fallback_list_format(self) -> None:
        """Fallback to numbered list when table rendering raises."""
        formulas = [
            {
                "formula_or_algorithm": "F = ma",
                "variables": "F, a, m",
                "source": "physics.pdf, p.12",
            }
        ]
        result = render_fallback_list(formulas)
        assert result.startswith("1.")
        assert "Formula/Algorithm: F = ma" in result
        assert "Variables: F, a, m" in result
        assert "Source: physics.pdf, p.12" in result

    def test_fallback_list_numbering(self) -> None:
        """Fallback list uses sequential numbering."""
        formulas = [
            {"formula_or_algorithm": "x = a", "variables": "a, x", "source": "s1"},
            {"formula_or_algorithm": "y = b", "variables": "b, y", "source": "s2"},
        ]
        result = render_fallback_list(formulas)
        assert "1." in result
        assert "2." in result


class TestBuildRenderedTable:
    """Tests for build_rendered_table fallback logic."""

    def test_returns_table_when_rendering_succeeds(self) -> None:
        formulas = [
            {"formula_or_algorithm": "F = ma", "variables": "F, a, m", "source": "p.pdf, p.1"}
        ]
        result = build_rendered_table(formulas)
        assert "| Formula/Algorithm |" in result

    def test_falls_back_to_list_when_render_raises(self, monkeypatch) -> None:
        """build_rendered_table falls back to numbered list when render_markdown_table raises."""
        formulas = [
            {"formula_or_algorithm": "F = ma", "variables": "F, a, m", "source": "p.pdf, p.1"}
        ]

        def bad_render(_: list) -> str:
            raise RuntimeError("simulated rendering failure")

        monkeypatch.setattr(
            "app.services.knowledge_store.formula_service.render_markdown_table",
            bad_render,
        )
        result = build_rendered_table(formulas)
        # Should fall back to numbered list
        assert "1." in result
        assert "F = ma" in result


# ===========================================================================
# HTTP endpoint tests
# ===========================================================================


class TestGetFormulas:
    """Tests for GET /formulas/{subject_id}."""

    @pytest.mark.asyncio
    async def test_returns_subject_id_formulas_and_table(self, client: AsyncClient) -> None:
        """GET /formulas/{subject_id} returns subject_id, formulas list, rendered_table."""
        subject_id = uuid.uuid4()
        chunks = [
            {"chunk_text": "F = ma is Newton's second law.", "filename": "phys.pdf", "page_number": 5},
        ]
        _, mock_cm = _make_db_mock_with_chunks(chunks)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/formulas/{subject_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["subject_id"] == str(subject_id)
        assert "formulas" in body
        assert isinstance(body["formulas"], list)
        assert "rendered_table" in body
        assert isinstance(body["rendered_table"], str)

    @pytest.mark.asyncio
    async def test_empty_subject_returns_empty_formulas(self, client: AsyncClient) -> None:
        """Subject with no chunks returns empty formulas list."""
        subject_id = uuid.uuid4()
        _, mock_cm = _make_empty_db_mock()

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/formulas/{subject_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["formulas"] == []

    @pytest.mark.asyncio
    async def test_latex_formula_appears_in_response(self, client: AsyncClient) -> None:
        """LaTeX formula in chunk text appears in formulas list."""
        subject_id = uuid.uuid4()
        chunks = [
            {
                "chunk_text": r"The derivative is \frac{dy}{dx} = n * x^(n-1)",
                "filename": "calc.pdf",
                "page_number": 3,
            }
        ]
        _, mock_cm = _make_db_mock_with_chunks(chunks)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/formulas/{subject_id}")

        assert resp.status_code == 200
        body = resp.json()
        formulas_text = " ".join(f["formula_or_algorithm"] for f in body["formulas"])
        assert "frac" in formulas_text or "=" in formulas_text


class TestPostFormulasScan:
    """Tests for POST /formulas/{subject_id}/scan."""

    @pytest.mark.asyncio
    async def test_scan_returns_status_completed(self, client: AsyncClient) -> None:
        """POST /formulas/{subject_id}/scan returns status='completed'."""
        subject_id = uuid.uuid4()
        _, mock_cm = _make_empty_db_mock()

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.post(f"/formulas/{subject_id}/scan")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

    @pytest.mark.asyncio
    async def test_scan_returns_subject_id_and_formula_count(self, client: AsyncClient) -> None:
        """POST /formulas/{subject_id}/scan returns subject_id and formula_count."""
        subject_id = uuid.uuid4()
        chunks = [
            {"chunk_text": "F = ma", "filename": "phys.pdf", "page_number": 1},
        ]
        _, mock_cm = _make_db_mock_with_chunks(chunks)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.post(f"/formulas/{subject_id}/scan")

        assert resp.status_code == 200
        body = resp.json()
        assert body["subject_id"] == str(subject_id)
        assert "formula_count" in body
        assert isinstance(body["formula_count"], int)

    @pytest.mark.asyncio
    async def test_scan_empty_subject_returns_zero_count(self, client: AsyncClient) -> None:
        """Re-scan on a subject with no chunks returns formula_count=0."""
        subject_id = uuid.uuid4()
        _, mock_cm = _make_empty_db_mock()

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.post(f"/formulas/{subject_id}/scan")

        body = resp.json()
        assert body["formula_count"] == 0
        assert body["status"] == "completed"


class TestGetFormulasExport:
    """Tests for GET /formulas/{subject_id}/export."""

    @pytest.mark.asyncio
    async def test_export_returns_content_disposition_attachment(
        self, client: AsyncClient
    ) -> None:
        """GET /formulas/{subject_id}/export returns Content-Disposition attachment header."""
        subject_id = uuid.uuid4()
        _, mock_cm = _make_empty_db_mock()

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/formulas/{subject_id}/export")

        assert resp.status_code == 200
        content_disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in content_disposition

    @pytest.mark.asyncio
    async def test_export_filename_contains_subject_id(self, client: AsyncClient) -> None:
        """Export filename includes the subject_id."""
        subject_id = uuid.uuid4()
        _, mock_cm = _make_empty_db_mock()

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/formulas/{subject_id}/export")

        assert resp.status_code == 200
        content_disposition = resp.headers.get("content-disposition", "")
        assert str(subject_id) in content_disposition

    @pytest.mark.asyncio
    async def test_export_returns_markdown_content(self, client: AsyncClient) -> None:
        """Export response body is Markdown (text/markdown content type)."""
        subject_id = uuid.uuid4()
        chunks = [
            {"chunk_text": "F = ma", "filename": "phys.pdf", "page_number": 1},
        ]
        _, mock_cm = _make_db_mock_with_chunks(chunks)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/formulas/{subject_id}/export")

        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "markdown" in content_type or "text" in content_type

    @pytest.mark.asyncio
    async def test_export_body_contains_formula_data(self, client: AsyncClient) -> None:
        """Export body contains formula data for subjects that have chunks."""
        subject_id = uuid.uuid4()
        chunks = [
            {"chunk_text": "E = m * c^2", "filename": "einstein.pdf", "page_number": 7},
        ]
        _, mock_cm = _make_db_mock_with_chunks(chunks)

        with patch("app.services.knowledge_store.router.get_db", return_value=mock_cm):
            resp = await client.get(f"/formulas/{subject_id}/export")

        assert resp.status_code == 200
        body_text = resp.text
        # The exported markdown should contain the formula expression
        assert "=" in body_text
