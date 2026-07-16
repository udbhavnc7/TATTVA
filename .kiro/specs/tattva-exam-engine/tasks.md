# Implementation Plan

## Overview

This plan implements the Tattva Exam Engine — an AI-powered exam preparation platform for engineering students. It covers the full Phase 1 core pipeline (ingestion → parsing → classification → generation → validation), the Phase 3 downstream services (PYQ Analyzer, Mock Paper Assembler, Spaced Repetition, Coverage Tracker, Formula Scanner), and all six UI screens in Next.js. Property-based tests (Hypothesis / fast-check) are co-located with each service to validate the 30 correctness properties defined in the design document.

## Tasks

- [x] 1. Project Scaffolding and Database Setup
  Set up the monorepo structure, configure PostgreSQL + pgvector, and establish the development environment.
  - [x] 1.1 Initialize FastAPI backend project with Poetry and folder structure (`services/ingestion`, `services/parsing`, `services/classification`, `services/generation`, `services/knowledge_store`) plus a shared `db/` module.
  - [x] 1.2 Initialize Next.js 14 frontend project with Tailwind CSS and shadcn/ui configured with the dark theme (black/dark-gray backgrounds, `#C9A84C` gold accent, white text).
  - [x] 1.3 Write the full PostgreSQL schema as Alembic migration scripts: `subjects`, `modules`, `topics`, `documents`, `chunks`, `notes`, `note_versions`, `validation_flags`, `pyqs`, `topic_importance`, `flashcards`, `classifications`, `oauth_tokens`.
  - [x] 1.4 Enable the `pgvector` extension and create the `chunks.embedding vector(1536)` column with an `ivfflat` index (`lists=100`).
  - [x] 1.5 Create a `docker-compose.yml` that runs PostgreSQL 15 + pgvector alongside the FastAPI dev server and verify the backend connection.
  - [x] 1.6 Configure pytest with `hypothesis` (`@settings(max_examples=100)`) and Vitest + Testing Library for the frontend; add a CI-ready test runner script.

- [x] 2. Ingestion Service
  Implement PDF ingestion including validation, deduplication, subject association, and document management endpoints.
  - [x] 2.1 Implement `POST /ingest` — accept `multipart/form-data` with `file` and optional `subject_id`; validate `application/pdf` content-type and ≤ 50 MB size; return `400` with `"file_type_invalid"` or `"file_size_exceeded"` on failure.
  - [x] 2.2 Implement SHA-256 content-hash computation over raw file bytes; store a `documents` record with `filename`, `uploaded_at`, `subject_id`, `source_type`, and `content_hash`; return `{ document_id: UUID }` on success.
  - [x] 2.3 Implement duplicate detection — if a document with the same `content_hash` already exists, return `409 Conflict` with `{ error: "duplicate_content", existing_document_id }` and write no new record.
  - [x] 2.4 Implement `GET /documents` and `DELETE /documents/{document_id}` endpoints.
  - [x] 2.5 Write property-based tests (Hypothesis) for Property 1 (file validation predicate), Property 2 (SHA-256 dedupe idempotency), Property 3 (valid upload returns UUID document_id), and Property 4 (hash determinism) — min 100 examples each.
  - [x] 2.6 Write unit tests for: valid upload happy path, each rejection reason (type, size, duplicate), and partial storage failure rollback.

- [x] 3. PDF Parsing Service
  Extract text, headings, formulas, tables, and figures from PDFs; produce token-bounded chunks with page attribution.
  - [x] 3.1 Implement PyMuPDF-based text extraction per page — extract headings, body text, formulas, tables, and figure regions with bounding boxes and caption text; record page number for every segment.
  - [x] 3.2 Implement Tesseract OCR fallback — apply OCR only on pages yielding zero characters from PyMuPDF; log unprocessable pages as `{ document_id, page_number, reason: "no_text_extracted" }`.
  - [x] 3.3 Implement the sliding-window sentence-boundary chunk splitter (400–600 tokens, hard-split at 600 with `[truncated]` marker, merge final chunks below 400 tokens with the previous); each chunk carries `{ document_id, page_number, text, token_count }`.
  - [x] 3.4 Store all chunks to the Knowledge Store; if any single chunk write fails, halt storage for the document, rollback, and surface an error with the document ID.
  - [x] 3.5 Write property-based tests for Property 5 (every chunk has a valid page number in `[1, N]`) and Property 6 (chunk token counts in `[400, 600]` except last-chunk merge) — min 100 examples each.
  - [x] 3.6 Write unit tests for: OCR fallback trigger, blank-page logging, sentence-boundary splitting, and final-chunk merging.

- [ ] 4. Classification Service
  Map parsed content to the subject/module/topic taxonomy using LLM; create new taxonomy records; flag low-confidence results for review.
  - [ ] 4.1 Implement the LLM classification prompt (`C1`) call — input is document headings and content; output must conform to the JSON schema `{ subject, module_number, topic, is_new_topic, confidence, note? }`.
  - [ ] 4.2 Implement single-retry logic on LLM error or JSON parse failure; mark document `classification_failed` and halt after both attempts fail.
  - [ ] 4.3 Implement taxonomy record creation — write new `subjects`, `modules`, and `topics` rows in a single atomic transaction **before** the document proceeds to chunking; enforce foreign-key ordering.
  - [ ] 4.4 Implement low-confidence handling — set `pending_review = true` and populate `note` (max 200 chars) on the `classifications` record when `confidence == "low"`.
  - [ ] 4.5 Write property-based tests for Property 7 (classification output always conforms to schema) and Property 8 (low-confidence `note` is present and ≤ 200 chars) — min 100 examples each.
  - [ ] 4.6 Write unit tests for: high/medium/low confidence paths, retry-then-fail path, and new taxonomy record creation order.

- [ ] 5. Knowledge Store — CRUD, Semantic Search, and Subject Management
  Implement all Knowledge Store endpoints including semantic search, subject/module CRUD, and chunk tagging enforcement.
  - [ ] 5.1 Implement `POST /subjects` and `GET /subjects` — enforce uniqueness on subject `code` (4–10 alphanumeric characters); return `409` with duplicate-code error on conflict.
  - [ ] 5.2 Implement `POST /subjects/{id}/modules` and `GET /subjects/{id}/modules`.
  - [ ] 5.3 Implement `GET /topics/{topic_id}` endpoint.
  - [ ] 5.4 Implement `GET /search?q=<text>&topic_id=<UUID>&k=<integer>` — generate query embedding, run pgvector cosine similarity search filtered by `topic_id`, return top-k results sorted descending by similarity including `source_filename`, `page_number`, `chunk_id`, `text`, and `cosine_similarity`; default `k=5`; return `500` on search failure.
  - [ ] 5.5 Enforce that every stored chunk carries non-null `subject_id`, `module_id`, `topic_id`, `document_id`, and `page_number`.
  - [ ] 5.6 Write property-based tests for Property 12 (every chunk carries all five required tags), Property 13 (search results correctly ordered and attributed), and Property 14 (subject code uniqueness invariant) — min 100 examples each.

- [ ] 6. Incremental Diff Pipeline and Version History
  Implement content-hash diffing so only changed topic blocks trigger re-generation; all regenerations produce immutable version records.
  - [ ] 6.1 Implement per-topic SHA-256 hash computation from normalized topic text (strip leading/trailing whitespace, collapse internal whitespace, NFC Unicode normalize).
  - [ ] 6.2 Implement hash comparison logic — skip all downstream steps on hash match; run the full pipeline on first ingestion (no stored hash) or hash change.
  - [ ] 6.3 On hash change: increment `topics.version`, store new `content_hash`, write a `note_versions` record (`version`, `timestamp`, `source_document_id`); roll back the entire regeneration if the `note_versions` write fails.
  - [ ] 6.4 Implement the `force_regenerate=true` flag on `POST /generate-notes` to bypass hash comparison unconditionally.
  - [ ] 6.5 Enforce minimum 10 historical `note_versions` records per topic; never delete `note_versions` rows.
  - [ ] 6.6 Write property-based tests for Property 9 (unchanged hash causes no downstream processing), Property 10 (changed hash triggers version increment), and Property 11 (version history is monotonically growing) — min 100 examples each.

- [ ] 7. Grounded Note Generation Service
  Implement RAG-grounded note generation at three depths with citation enforcement, confidence self-assessment, and the similarity-gate refusal.
  - [ ] 7.1 Implement `POST /generate-notes` — validate `topic_id` (UUID, must exist) and `depth` (`2mark` | `6mark` | `10mark`); return `400` for invalid inputs without triggering retrieval.
  - [ ] 7.2 Implement retrieval: call `GET /search` for top-5 chunks scoped to `topic_id`; gate generation if `max(cosine_similarity) < 0.5` — return `422 "Not covered in provided material"` and write no note record.
  - [ ] 7.3 Implement depth-tiered generation prompt (`C2`) — 2-mark: 2–4 sentences; 6-mark: definition + explanation + example; 10-mark: definition, 3+ sub-points, worked example, diagram reference, advantages/comparison; every paragraph must include a `(Source: filename.pdf, p.N)` citation.
  - [ ] 7.4 Parse the `CONFIDENCE: grounded|partial|needs_review` line from LLM output and store it as the initial `confidence` badge.
  - [ ] 7.5 Store the note record (`topic_id`, `version`, `depth`, `content_md`, `confidence`, `generated_at`) only after the Confidence Validator completes; return `{ note_id, confidence, content_md }` on success.
  - [ ] 7.6 Implement `GET /notes/{topic_id}` and `POST /topics/{id}/regenerate` endpoints.
  - [ ] 7.7 Write property-based tests for Property 15 (low similarity triggers refusal, no note written), Property 16 (every paragraph has a citation), and Property 17 (confidence badge is always a valid value) — min 100 examples each.
  - [ ] 7.8 Write unit tests for: each depth level output structure, refusal when similarity < 0.5, and LLM failure rollback.

- [ ] 8. Confidence Validator
  Implement the second-pass hallucination-detection validator; flag unsupported sentences and downgrade badges.
  - [ ] 8.1 Implement the Confidence Validator using prompt `C8` — second LLM call (cheaper/faster model) that checks each note sentence against cited chunks; flag sentences with cosine similarity < 0.5 against all cited chunks as unsupported.
  - [ ] 8.2 Implement badge downgrade logic — if any unsupported sentence is found, unconditionally set `confidence = "needs_review"` on the note record regardless of self-assessed badge.
  - [ ] 8.3 Store flagged sentences in the `validation_flags` table (`note_id`, `flagged_sentence`, `flagged_at`); never embed flags in note content.
  - [ ] 8.4 Implement validator failure handling — if the LLM call fails or times out (> 30 seconds), preserve the existing badge unchanged and log the failure with `note_id`; do not abort note storage.
  - [ ] 8.5 Enforce validator is read-only on `content_md` — the note text must never be modified.
  - [ ] 8.6 Write property-based tests for Property 18 (validator only downgrades, never upgrades) and Property 19 (validator does not mutate note content) — min 100 examples each.

- [ ] 9. Syllabus Coverage Tracker
  Compute and expose real-time coverage metrics via `GET /coverage`.
  - [ ] 9.1 Implement `GET /coverage` — return `grounded_count`, `partial_count`, `needs_review_count`, `no_notes_count`, `total_topics`, and `coverage_percentage` using formula `round((grounded_count / total_topics) * 100)`.
  - [ ] 9.2 Implement a database trigger or background refresh so coverage metrics update within 5 seconds after any note is generated or a badge changes — no manual page refresh required.
  - [ ] 9.3 Expose per-topic badge status in the coverage endpoint to support the syllabus outline UI.
  - [ ] 9.4 Write property-based tests for Property 20 (coverage percentage matches formula for any badge distribution) — min 100 examples.

- [ ] 10. PYQ Analyzer
  Implement PYQ ingestion, LLM-based topic matching, deterministic SQL importance scoring, and frequency data endpoints.
  - [ ] 10.1 Implement `POST /pyqs` — validate fields: `year` (2000–current year), `marks` (1–100), `question_text` (10–2000 characters); return `400` identifying the specific invalid field on failure.
  - [ ] 10.2 Implement LLM topic matching (prompt `C5`) — set `topic_id` on match; set `topic_id = null` and `is_unmatched = true` when no match has sufficient confidence.
  - [ ] 10.3 Store estimated `difficulty` (`easy` | `medium` | `hard`) and `difficulty_note` (≤ 200 chars) per PYQ for audit; store `secondary_topics` array.
  - [ ] 10.4 Implement `POST /pyqs/recalculate` — run the deterministic SQL `COUNT(*) GROUP BY topic_id` upsert into `topic_importance`; must complete in ≤ 10 seconds for 500 PYQ records; frequency counting must never be delegated to an LLM.
  - [ ] 10.5 Implement `GET /pyqs` with filters and `GET /topics/{id}/importance`.
  - [ ] 10.6 Write property-based tests for Property 21 (PYQ field validation predicate), Property 22 (topic importance deterministically computed), and Property 23 (unseen topics default to `frequency_count = 0`) — min 100 examples each.
  - [ ] 10.7 Write unit tests for: valid/invalid field combinations, unmatched topic handling, and SQL count verification.

- [ ] 11. Mock Exam Paper Assembler
  Implement PYQ-weighted mock paper assembly with importance ordering, tie-breaking, and insufficient-bank handling.
  - [ ] 11.1 Implement `POST /mock-paper` — accept `subject_id`, `total_marks_target` (positive integer), and `question_type_distribution` (e.g., `2×10mark + 4×6mark + 4×2mark`).
  - [ ] 11.2 Implement selection logic — rank unique questions by `topic_importance` descending; break ties by most recent year; select uniformly at random if all scores are 0.
  - [ ] 11.3 Finalize the paper when `total_marks_target` is reached even if the distribution is not exactly satisfied.
  - [ ] 11.4 If the PYQ bank cannot satisfy the minimum distribution, assemble with all available questions and return a warning listing unsatisfied question types; do not abort silently.
  - [ ] 11.5 Return assembled questions ordered by marks descending with `topic_tag` and `marks` per question.
  - [ ] 11.6 Write property-based tests for Property 24 (mock paper ordering respects topic importance; ties broken by year) — min 100 examples.
  - [ ] 11.7 Write unit tests for: importance-ordered selection, tie-breaking by year, and insufficient-bank warning.

- [ ] 12. Spaced Repetition Flashcard System
  Implement flashcard generation from notes, SM-2 scheduling, and all flashcard endpoints.
  - [ ] 12.1 Implement automatic flashcard generation after note creation — 4–6 flashcards per note; card front is a single focused question; card back is ≤ 40 words with a `(Source: filename.pdf, p.N)` citation; use only content from the generated note.
  - [ ] 12.2 Implement the SM-2 update function as a pure function: `new_ef = max(1.3, ef + 0.1 - (5-q)*(0.08 + (5-q)*0.02))` with interval logic (q<3 → interval=1; q>=3 → 1/6/ef×interval on 0/1/N+ repetitions).
  - [ ] 12.3 Implement `POST /flashcards/{id}/review` — accept `recall_score` (0–5); reject with a validation error if out of range; update `ease_factor`, `interval_days`, `repetitions`, `next_review_at`.
  - [ ] 12.4 Implement `GET /flashcards?topic_id=&due_only=` — return card count and due count (cards where `next_review_at <= now()`).
  - [ ] 12.5 Write property-based tests for Property 25 (flashcard count per note is 4–6), Property 26 (initial ease_factor is 2.5), Property 27 (SM-2 update is deterministic and correct), and Property 28 (invalid recall score rejected, state unchanged) — min 100 examples each.
  - [ ] 12.6 Write unit tests for: recall score 0 restart, recall score 5 max-EF, and `next_review_at` is always in the future.

- [ ] 13. Formula Scanner
  Extract formulas, equations, and algorithm pseudocode from chunks; expose as a structured downloadable Markdown table.
  - [ ] 13.1 Implement `GET /formulas/{subject_id}` — scan chunks for the subject, extract every formula/equation/algorithm pseudocode; flag incomplete formulas as `[incomplete in source]` without completing them.
  - [ ] 13.2 Render results as a Markdown table with columns: `Formula/Algorithm`, `Variables`, `Source`; fall back to a numbered list with the same three fields if table rendering fails.
  - [ ] 13.3 Implement `POST /formulas/{subject_id}/scan` — re-run extraction against current Knowledge Store state and return a completion notification.
  - [ ] 13.4 Implement `GET /formulas/{subject_id}/export` — return the formula table as a downloadable `.md` file.

- [ ] 14. Parser/Serializer Round-Trip Integrity Tests
  Verify that chunk and note objects survive database serialize/deserialize with no field mutation (Properties 29 and 30).
  - [ ] 14.1 Implement `tests/test_round_trip.py` — chunk round-trip: serialize `Chunk(text, page_number, document_id, topic_id)` to the `chunks` table and deserialize; assert all four fields identical. Min 100 randomly generated valid inputs via `st.builds(Chunk, ...)`.
  - [ ] 14.2 Implement note round-trip: serialize `Note(content_md, confidence, depth, topic_id, generated_at)` to the `notes` table and deserialize; assert all five fields identical. Min 100 randomly generated valid inputs.
  - [ ] 14.3 Tag both tests as Property 29 and Property 30 with `@settings(max_examples=100)` and `Feature: tattva-exam-engine` docstrings.

- [ ] 15. Next.js UI — Shared Layout and Navigation
  Build the persistent dark-themed sidebar and global layout used by all six screens.
  - [ ] 15.1 Implement the global dark-theme layout (`black`/`dark-gray` backgrounds, `#C9A84C` gold accent, white text) using Tailwind CSS variables and shadcn/ui tokens.
  - [ ] 15.2 Implement the persistent sidebar with navigation links to all six screens: Syllabus Coverage, Grounded Notes, PYQ Exam Paper, Spaced Repetition, Socratic Q&A, Formula Sheet; visually indicate the active screen.
  - [ ] 15.3 Ensure all interactive controls meet a minimum 44×44 CSS pixels tap/click target size and the layout is usable at ≥ 1280px desktop viewports.
  - [ ] 15.4 Write Vitest + Testing Library tests confirming the sidebar renders all six links and the active link receives the correct visual indicator class.

- [ ] 16. UI — Syllabus Coverage Dashboard
  Build the main dashboard with circular gauge, stats grid, file panel, and syllabus outline with per-topic badges.
  - [ ] 16.1 Implement the circular progress gauge displaying the AI-grounded completeness percentage from `GET /coverage`.
  - [ ] 16.2 Implement the stats grid showing counts for `grounded`, `partial`, `needs_review`, and no-notes topics.
  - [ ] 16.3 Implement the file panel listing all uploaded documents from `GET /documents`.
  - [ ] 16.4 Implement the syllabus outline showing all modules and topics with `grounded` / `partial` / `needs_review` / missing badges.
  - [ ] 16.5 Implement live update — poll or subscribe so metrics refresh within 5 seconds after note generation without manual page refresh.
  - [ ] 16.6 Write Vitest tests confirming the gauge renders the correct percentage and the stats grid shows correct counts for known badge distributions.

- [ ] 17. UI — Grounded Notes Screen
  Build the module/topic browser, note display with depth tabs, confidence badges, verified-sources panel, and generate button.
  - [ ] 17.1 Implement the left panel listing all modules; expand to show topics on module selection.
  - [ ] 17.2 Implement the right panel with depth tabs (2-mark / 6-mark / 10-mark); show note content for the selected topic and depth; display "no note available" prompt with Generate button when no note exists.
  - [ ] 17.3 Disable the "Generate Grounded Study Notes" button when no topic is selected; enable on topic selection and wire to `POST /generate-notes`.
  - [ ] 17.4 Display the confidence badge (`Grounded` / `Partially Grounded` / `Needs Review`) alongside each note.
  - [ ] 17.5 Display the "Verified Sources" panel listing cited documents and page numbers for `grounded`/`partial` notes; show "no verified sources available" for `needs_review` notes.
  - [ ] 17.6 Display the "Note Architecture Rules" sidebar on all note views.
  - [ ] 17.7 Render a visible amber border and warning icon on `needs_review` note cards.
  - [ ] 17.8 Write Vitest tests for: confidence badge variant rendering, `needs_review` amber border, and disabled/enabled Generate button state.

- [ ] 18. UI — PYQ Exam Paper Screen
  Build the PYQ ingestion form, Topic Frequency Analysis table, and Historical Question Library.
  - [ ] 18.1 Implement the "Ingest Past Question" form with validated fields (year, marks, question text) and inline error messages identifying the specific invalid field.
  - [ ] 18.2 Implement the Topic Frequency Analysis table — columns: topic name, asked count, difficulty color bar (red=hard, amber=medium, green=easy), reference weight.
  - [ ] 18.3 Implement the Historical Question Library listing each PYQ with year and difficulty badge.
  - [ ] 18.4 Implement the "Map & Recalculate Importance" button wired to `POST /pyqs/recalculate`; show a loading indicator during recalculation.

- [ ] 19. UI — Spaced Repetition Screen
  Build the flashcard study center with SM-2 metadata display, topic filter, and recall score submission.
  - [ ] 19.1 Implement the flashcard study center showing: question front, recall score input (0–5), "Submit" action, topic tag, and "Reveal Spaced Repetition Answer" button.
  - [ ] 19.2 Implement the topic dropdown filter; update card count and due count immediately when the filter changes.
  - [ ] 19.3 Display SM-2 metadata: total cards in the selected deck and cards due (`next_review_at <= now()`).
  - [ ] 19.4 Write Vitest tests for: filter updates card/due counts immediately, and recall score input enforces the 0–5 range.

- [ ] 20. UI — Formula Sheet Screen
  Build the formula sheet UI with KaTeX rendering, re-scan action, and Markdown export.
  - [ ] 20.1 Implement subject selector; on selection call `GET /formulas/{subject_id}` and display the formula table.
  - [ ] 20.2 Render equations using KaTeX so mathematical notation is human-readable rather than raw LaTeX strings.
  - [ ] 20.3 Implement "Re-Scan Textbooks" button wired to `POST /formulas/{subject_id}/scan`; display a visible completion notification when the scan finishes.
  - [ ] 20.4 Implement "Export Equation Table" button wired to `GET /formulas/{subject_id}/export` to trigger the `.md` file download.

- [ ] 21. Integration Tests
  Verify end-to-end pipeline correctness against a real PostgreSQL + pgvector Docker instance.
  - [ ] 21.1 End-to-end test: PDF upload → parse → classify → generate note → validate → retrieve note via API; assert confidence badge and citations are present.
  - [ ] 21.2 Confidence Validator timing test: assert P95 completion < 30 seconds on representative note sizes.
  - [ ] 21.3 Coverage Tracker latency test: assert metrics update within 5 seconds after note generation without manual refresh.
  - [ ] 21.4 PYQ importance recalculation performance test: assert 500 PYQ records complete within 10 seconds.
  - [ ] 21.5 Version history integrity test: ingest the same document with modified content 3 times; assert 3 `note_versions` records with strictly increasing version numbers and no rows deleted.

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"] },
    { "wave": 2, "tasks": ["2", "3", "5", "15"] },
    { "wave": 3, "tasks": ["4", "10", "13"] },
    { "wave": 4, "tasks": ["6", "11"] },
    { "wave": 5, "tasks": ["7"] },
    { "wave": 6, "tasks": ["8", "12", "14"] },
    { "wave": 7, "tasks": ["9"] },
    { "wave": 8, "tasks": ["16", "17", "18", "19", "20"] },
    { "wave": 9, "tasks": ["21"] }
  ]
}
```

## Notes

- Phase 2 features (Google Drive OAuth, incremental polling, watch channels) are scaffolded in the schema (Task 1.3) and API surface (Task 2) but implementation is deferred to a follow-on spec.
- Phase 4 features (Mermaid diagrams, Socratic Q&A, TTS, Notion/Obsidian/Anki export) are represented by the schema columns (`mermaid_code`, `audio_cache_key`) but full implementation is deferred.
- All property-based tests must use the `@settings(max_examples=100)` decorator and include a `Feature: tattva-exam-engine, Property N: <description>` docstring per the testing strategy in the design document.
- The SM-2 pure function (Task 12.2) is an ideal candidate for property-based testing first; implement and test it before wiring up the review endpoint.
