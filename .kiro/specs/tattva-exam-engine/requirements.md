# Requirements Document

## Introduction

Tattva is an AI-powered exam preparation platform for engineering students. It ingests lecture PDFs, parses and classifies their content into a subject/module/topic taxonomy, generates RAG-grounded study notes at three exam depths (2-mark, 6-mark, 10-mark), tracks Previous Year Question (PYQ) frequency, and surfaces everything through a dark-themed web UI. The core differentiator is that every generated note is grounded — every claim cites the exact source page it came from. The system explicitly refuses to fill knowledge gaps from LLM training data.

Tattva is built in four phases:
- **Phase 1:** Manual PDF upload → parse → classify → grounded note generation → citations.
- **Phase 2:** Drive/Classroom OAuth ingestion, incremental diffing, version history, notifications.
- **Phase 3:** PYQ analyzer, mock paper assembler, spaced-repetition flashcards, syllabus coverage tracker, formula scanner.
- **Phase 4:** Mermaid diagrams inline, Socratic Q&A chat, TTS audio overview, export to Notion/Obsidian/Anki.

---

## Glossary

- **Tattva**: The AI-powered exam preparation platform being specified in this document.
- **Ingestion_Service**: The component responsible for receiving, hashing, deduplicating, and storing uploaded or remotely discovered PDF files.
- **Parser**: The component that extracts text, headings, formulas, tables, and page structure from PDF documents using PyMuPDF, pdfplumber, or Tesseract OCR.
- **Classifier**: The LLM-backed component that maps extracted document content to the subject/module/topic taxonomy.
- **Knowledge_Store**: The Postgres + pgvector database that stores all chunks tagged with subject, module, topic, source document, and page number.
- **Generation_Service**: The RAG-grounded LLM component that produces study notes, formula sheets, Mermaid diagrams, and flashcards from retrieved chunks.
- **Confidence_Validator**: The second-pass LLM check that reviews generated notes against cited chunks and flags unsupported sentences.
- **PYQ_Analyzer**: The component that ingests past year exam question papers, matches questions to topics via LLM, and computes topic importance via deterministic SQL aggregation.
- **Spaced_Repetition_Scheduler**: The SM-2 algorithm component that manages flashcard review scheduling.
- **Socratic_Solver**: The chat component that answers student questions exclusively from the subject's retrieved chunks.
- **Formula_Scanner**: The component that extracts formulas, equations, and algorithm pseudocode from chunks and renders them in a structured table.
- **Mock_Paper_Assembler**: The component that selects PYQ-style questions weighted by topic importance to generate a practice exam paper.
- **Coverage_Tracker**: The component that computes the percentage of topics per module that have grounded, partial, or missing notes.
- **Subject**: A top-level course unit (e.g., Operating Systems).
- **Module**: A numbered chapter or section within a subject.
- **Topic**: A discrete concept within a module that is the atomic unit of note generation.
- **Chunk**: A segment of parsed text between 400 and 600 tokens, stored with its source document ID and page number.
- **Depth**: One of three note generation tiers — `2mark`, `6mark`, or `10mark` — corresponding to exam answer lengths.
- **Confidence_Badge**: A label assigned to each generated note: `grounded`, `partial`, or `needs_review`.
- **PYQ**: Previous Year Question — an exam question from a past year's paper.
- **Topic_Importance**: A computed score per topic derived from PYQ frequency count and average difficulty.
- **Content_Hash**: A SHA-256 hash of normalized parsed text used to detect when a topic's source material has changed.
- **Google_Drive_Watcher**: The Drive API push-notification channel that detects new files in a configured folder.
- **SM-2**: The SuperMemo 2 spaced-repetition algorithm used to schedule flashcard reviews.

---

## Requirements

### Requirement 1: PDF Ingestion

**User Story:** As a student, I want to upload lecture PDFs manually so that Tattva can process them and build my knowledge store.

#### Acceptance Criteria

1. WHEN a student submits a file via the drag-and-drop upload zone or a `POST /ingest` API call, THE Ingestion_Service SHALL accept the file if and only if it is a PDF with a size of 50 MB or less.
2. IF the submitted file is not a PDF or exceeds 50 MB, THEN THE Ingestion_Service SHALL reject it immediately with an error identifying whether the rejection was due to file type or file size, and SHALL NOT begin storing any data.
3. WHEN a valid PDF file is accepted, THE Ingestion_Service SHALL compute a SHA-256 content hash and store a document record containing the filename, upload timestamp, subject association, source type, and content hash.
4. IF a file with an identical SHA-256 content hash already exists in the Knowledge_Store for that student, THEN THE Ingestion_Service SHALL reject the upload and return a message indicating the file is already present, without creating a new document record.
5. WHEN a PDF file is successfully stored, THE Ingestion_Service SHALL return a document ID to the caller within the upload response.
6. IF a PDF file upload fails due to a network or storage error after the file has been accepted, THEN THE Ingestion_Service SHALL return a descriptive error message identifying the failure type and SHALL NOT create a partial document record.
7. WHEN a student submits a PDF, THE Ingestion_Service SHALL allow the student to optionally associate the document with an existing subject. IF no subject is selected, THE Ingestion_Service SHALL store the document without a subject association and classify it in a subsequent step.

---

### Requirement 2: Drive and Classroom OAuth Ingestion (Phase 2)

**User Story:** As a student, I want Tattva to automatically detect new PDFs in my Google Drive folder so that my knowledge store stays current without manual uploads.

#### Acceptance Criteria

1. WHERE Google OAuth2 integration is configured, THE Ingestion_Service SHALL authenticate using the student's own Google account credentials via OAuth2 consent and store the resulting access and refresh tokens.
2. WHERE Google Drive integration is configured, THE Ingestion_Service SHALL attempt to register a push notification watch channel on a specified Drive folder. IF watch channel registration fails, THE Ingestion_Service SHALL fall back to polling and log the registration failure with the error code.
3. WHEN a new PDF file appears in the watched Drive folder, THE Ingestion_Service SHALL automatically download the file and trigger the full ingestion pipeline without requiring manual user action.
4. WHEN a Drive-sourced file is fully downloaded, THE Ingestion_Service SHALL compute a SHA-256 hash and compare it against existing document records for that student. IF a match is found, THE Ingestion_Service SHALL discard the download without creating a new document record.
5. IF a Drive-sourced file download fails before completion, THEN THE Ingestion_Service SHALL retry up to 3 times at 60-second intervals. After 3 failed attempts, THE Ingestion_Service SHALL log the failure and treat the file as new on the next polling cycle, bypassing deduplication for that retry.
6. IF the Google Drive watch channel expires or encounters a rate-limit error, THEN THE Ingestion_Service SHALL fall back to polling the folder at a default interval of 5 minutes (configurable between 1 and 60 minutes) and SHALL log the fallback event with a timestamp.
7. THE Ingestion_Service SHALL operate exclusively with the OAuth2 scopes the authenticated student has explicitly consented to and SHALL NOT access any other user's data under any circumstances.
8. IF the student's OAuth2 session includes pre-consented scopes from a previous session, THEN THE Ingestion_Service SHALL use the stored refresh token to renew access without prompting the student again, provided the scope set has not changed.

---

### Requirement 3: PDF Parsing and Text Extraction

**User Story:** As a student, I want the system to accurately extract text and structure from my lecture PDFs so that notes are generated from real content.

#### Acceptance Criteria

1. WHEN a PDF document is ingested, THE Parser SHALL extract headings, body text, formulas, tables, and figure regions (including bounding box coordinates and associated caption text) using PyMuPDF as the primary parsing method.
2. WHEN a PDF page contains only images and no extractable text layer, THE Parser SHALL apply Tesseract OCR as a fallback to extract text from that page.
3. WHEN text is extracted from a page, THE Parser SHALL record the page number for every extracted text segment so that downstream citation is possible.
4. WHEN extraction produces text, THE Parser SHALL segment it into chunks of between 400 and 600 tokens each, with each chunk carrying its source page number as an attribute.
5. IF a page produces no extractable text through either PyMuPDF or OCR, THEN THE Parser SHALL mark that page as unprocessable and log an entry containing at minimum the document ID and page number — the page SHALL NOT be silently discarded.
6. WHEN parsing is complete, THE Parser SHALL store all chunks in the Knowledge_Store with their associated document ID and page number.
7. IF the Knowledge_Store write operation fails for any chunk, THEN THE Parser SHALL halt storage for the affected document, surface an error identifying the document ID, and SHALL NOT silently discard the unwritten chunks.

---

### Requirement 4: Content Classification

**User Story:** As a student, I want Tattva to automatically classify uploaded content into my subject/module/topic taxonomy so that notes are organized according to my syllabus.

#### Acceptance Criteria

1. WHEN parsed document headings and content are available, THE Classifier SHALL compare them against the stored taxonomy and produce a classification output in the JSON schema defined in criterion 6.
2. IF the Classifier determines a match with confidence `high`, THEN THE Classifier SHALL map the document to the matched existing subject, module, and topic entry without creating a new taxonomy record.
3. IF the Classifier determines confidence is `medium` or `low`, THEN THE Classifier SHALL propose a new module or topic entry and SHALL set the corresponding confidence level in the output JSON.
4. WHEN classification produces a new subject, module, or topic record, THE Classifier SHALL create those records in the Knowledge_Store before the document proceeds to the chunking step.
5. IF the Classifier returns a confidence level of `low`, THEN THE Classifier SHALL include a human-readable note (maximum 200 characters) explaining the uncertainty and SHALL flag the classification record for user review.
6. THE Classifier SHALL output structured JSON containing: `subject` (string), `module_number` (integer), `topic` (string), `is_new_topic` (boolean), `confidence` ("high" | "medium" | "low"), and `note` (string, optional).
7. IF the Classifier encounters an LLM error or returns malformed JSON, THEN THE Classifier SHALL retry once. If the second attempt also fails, THE Classifier SHALL mark the document as `classification_failed`, log the error, and halt further pipeline processing for that document.

---

### Requirement 5: Incremental Diffing and Version Control (Phase 2)

**User Story:** As a student, I want the system to regenerate notes only for content that has actually changed so that processing is efficient and my version history is preserved.

#### Acceptance Criteria

1. WHEN a document is parsed, THE Ingestion_Service SHALL compute a SHA-256 content hash for each classified topic block. IF no stored hash exists for that topic (first ingestion), THE Ingestion_Service SHALL treat it as a change and run the full pipeline.
2. IF the computed hash matches the stored hash for a topic, THEN THE Ingestion_Service SHALL skip all downstream processing steps for that topic.
3. IF the student explicitly requests manual regeneration for a topic, THEN THE Ingestion_Service SHALL run the full pipeline for that topic regardless of whether its hash has changed.
4. WHEN the computed hash differs from the stored hash for a topic, THE Ingestion_Service SHALL increment the topic's version number, store the new hash, and trigger re-generation for that topic only.
5. THE Knowledge_Store SHALL retain a minimum of 10 previous versions of a topic's notes per topic and SHALL NOT overwrite historical versions on update.
6. WHEN a topic is regenerated due to a content change, THE Ingestion_Service SHALL log a version history entry recording the version number, timestamp, and source document ID that triggered the change.
7. IF the Knowledge_Store write for a version history entry fails, THEN THE Ingestion_Service SHALL abort the regeneration for that topic and surface an error identifying the topic ID — it SHALL NOT proceed with generation without a version record.

---

### Requirement 6: Knowledge Store Management

**User Story:** As a student, I want all extracted content to be stored in a structured, searchable knowledge store so that notes can be grounded in my own material.

#### Acceptance Criteria

1. THE Knowledge_Store SHALL store subjects, modules, topics, documents, chunks, notes, PYQs, topic importance scores, and flashcards in a PostgreSQL database using the schema defined in the design document.
2. THE Knowledge_Store SHALL store vector embeddings for all chunks in a pgvector column of dimension 1536.
3. WHEN a chunk is stored, THE Knowledge_Store SHALL tag it with its subject ID, module ID, topic ID, source document ID, and page number.
4. WHEN a semantic search query is issued with a value of k, THE Knowledge_Store SHALL return the top-k chunks ranked by cosine similarity to the query embedding, including their source document filenames and page numbers. IF the search operation fails, THE Knowledge_Store SHALL return an error response — it SHALL NOT return partial or unranked results.
5. THE Knowledge_Store SHALL expose a `GET /search?q=<text>&k=<integer>` endpoint that returns matching chunks with source page attribution. IF k is not provided, THE Knowledge_Store SHALL default to k=5.
6. WHEN a student submits an "Add Subject" form with a subject code (4–10 alphanumeric characters) and a subject name (1–120 characters), THE Knowledge_Store SHALL create a new subject record. IF a subject with the same code already exists, THE Knowledge_Store SHALL reject the creation and return an error indicating the duplicate code.

---

### Requirement 7: Grounded Note Generation

**User Story:** As a student, I want Tattva to generate study notes at three exam depths so that I can prepare appropriate answers for 2-mark, 6-mark, and 10-mark questions.

#### Acceptance Criteria

1. WHEN a topic_id and depth level are provided, THE Generation_Service SHALL retrieve the top-5 most relevant chunks for that topic from the Knowledge_Store using pgvector cosine similarity search.
2. WHEN generating a 2-mark note, THE Generation_Service SHALL produce a crisp definition or answer of 2–4 sentences.
3. WHEN generating a 6-mark note, THE Generation_Service SHALL produce a definition, explanation, and at least one example or diagram reference.
4. WHEN generating a 10-mark note, THE Generation_Service SHALL produce a structured response covering: a definition, a minimum of 3 distinct sub-points, at least one worked example, at least one diagram reference, and an advantages/disadvantages or comparison section where applicable.
5. WHEN a note is generated, THE Generation_Service SHALL append a citation in the format `(Source: filename.pdf, p.N)` to every paragraph.
6. THE Generation_Service SHALL use only the retrieved chunks as the source of factual content and SHALL NOT add facts from the LLM's training data.
7. IF the cosine similarity of all top-5 retrieved chunks for a topic is below 0.5, THEN THE Generation_Service SHALL output "Not covered in provided material" and SHALL NOT attempt generation.
8. WHEN a note is successfully generated, THE Generation_Service SHALL self-assess and assign a confidence badge using the following rules: `grounded` if all claims are directly supported by cited chunks; `partial` if some claims are inferred or combined across chunks but remain source-consistent; `needs_review` if context was thin, ambiguous, or any claim is unsupported.
9. IF note generation fails due to an LLM error or empty retrieval, THE Generation_Service SHALL NOT write a note record and SHALL return an error identifying the topic_id and failure reason.
10. WHEN a note is stored in the Knowledge_Store, THE Generation_Service SHALL record the topic_id, version, depth, content in Markdown, confidence badge, and generation timestamp.
11. IF the `POST /generate-notes` endpoint receives an invalid topic_id or an unrecognized depth value, THEN THE Generation_Service SHALL return a 400 error identifying the invalid parameter without attempting retrieval or generation.

---

### Requirement 8: Confidence Validation (Anti-Hallucination)

**User Story:** As a student, I want the system to verify every generated note against its cited sources so that I can trust the accuracy of what I study.

#### Acceptance Criteria

1. WHEN a note is generated by THE Generation_Service, THE Confidence_Validator SHALL automatically perform a second-pass review of the note against its cited source chunks, completing within 30 seconds.
2. WHEN THE Confidence_Validator identifies a sentence in the note whose cosine similarity against all cited chunks is below 0.5, THE Confidence_Validator SHALL flag that sentence as unsupported.
3. WHEN one or more unsupported sentences are detected, THE Confidence_Validator SHALL downgrade the note's confidence badge to `needs_review` regardless of the confidence level self-reported in generation.
4. IF THE Confidence_Validator encounters a parsing error or LLM failure that prevents it from completing analysis, THEN THE Confidence_Validator SHALL leave the confidence badge unchanged and log the validator failure with the note ID — it SHALL NOT downgrade the badge based on an incomplete run.
5. WHEN THE Confidence_Validator flags unsupported sentences, THE Confidence_Validator SHALL log each flagged sentence with its note ID for user review.
6. IF the cosine similarity across the top-5 retrieved chunks for a topic is below 0.5 at retrieval time, THEN THE Generation_Service SHALL assign a confidence badge of `needs_review` and SHALL NOT attempt generation.
7. THE Confidence_Validator SHALL NOT rewrite or modify the note content — its role is flagging only.

---

### Requirement 9: Syllabus Coverage Dashboard

**User Story:** As a student, I want a visual overview of my syllabus coverage so that I can see at a glance which topics are fully grounded, partially covered, or missing.

#### Acceptance Criteria

1. THE Coverage_Tracker SHALL compute the AI-grounded completeness percentage as: (number of topics with a `grounded` confidence badge) ÷ (total number of topics in the syllabus) × 100, rounded to the nearest integer.
2. THE Coverage_Tracker SHALL display this percentage as a circular progress gauge on the main dashboard.
3. THE Coverage_Tracker SHALL display a stats grid on the main dashboard showing: count of topics with `grounded` badge, count with `partial` badge, count with `needs_review` badge, and count of topics with no notes generated yet.
4. THE Coverage_Tracker SHALL list all uploaded documents in the knowledge store file panel on the main dashboard.
5. THE Coverage_Tracker SHALL render the course syllabus outline with all modules and topics, and display each topic's `grounded`, `partial`, `needs_review`, or missing badge alongside its name.
6. WHEN a new note is generated or a confidence badge changes, THE Coverage_Tracker SHALL recalculate and update all coverage metrics and badge counts within 5 seconds without requiring a manual page refresh.

---

### Requirement 10: Grounded Notes UI

**User Story:** As a student, I want to browse notes organized by module and topic so that I can study efficiently by subject area.

#### Acceptance Criteria

1. THE Tattva UI SHALL display a left panel listing all modules and, on selection of a module, the topics within that module.
2. WHEN a topic is selected, THE Tattva UI SHALL display the available notes for that topic in a right panel with depth tabs for 2-mark, 6-mark, and 10-mark. IF no note exists for the selected topic and depth, THE Tattva UI SHALL display a prompt indicating no note is available and show the "Generate Grounded Study Notes" button.
3. IF no topic is selected, THEN THE Tattva UI SHALL disable the "Generate Grounded Study Notes" button. WHEN a topic is selected, THE Tattva UI SHALL enable the button and trigger note generation for the selected topic and depth on click.
4. WHEN a note is displayed, THE Tattva UI SHALL show the confidence badge (Grounded / Partially Grounded / Needs Review) alongside the note content.
5. WHEN a note is displayed and its confidence badge is `grounded` or `partial`, THE Tattva UI SHALL show a "Verified Sources" panel listing all cited source documents and page numbers. WHEN a note's confidence badge is `needs_review`, THE Tattva UI SHALL show a "Verified Sources" panel with a message stating no verified sources are available.
6. WHILE a note is displayed, THE Tattva UI SHALL show a "Note Architecture Rules" sidebar explaining the three grounding rules applied to all generated notes.
7. WHEN a note's confidence badge is `needs_review`, THE Tattva UI SHALL render a visible warning indicator (such as a distinct amber border or warning icon) on the note card to distinguish it from grounded notes.

---

### Requirement 11: PYQ Ingestion and Topic Matching

**User Story:** As a student, I want to ingest past year question papers so that Tattva can track which topics are most frequently examined.

#### Acceptance Criteria

1. THE PYQ_Analyzer SHALL accept PYQ submissions via a dedicated "Ingest Past Question" form with the following validated fields: year (4-digit integer, 2000–current year), marks (positive integer, 1–100), and question text (10–2000 characters). IF any field is invalid, THE PYQ_Analyzer SHALL reject the submission and identify the invalid field.
2. WHEN a valid PYQ is submitted, THE PYQ_Analyzer SHALL match the question to a primary topic in the stored taxonomy using an LLM prompt and SHALL record any secondary topics separately.
3. IF the LLM finds no matching topic with sufficient confidence, THEN THE PYQ_Analyzer SHALL store the PYQ with a `topic_id` of null and flag it as unmatched for manual review.
4. WHEN a PYQ is matched to a topic, THE PYQ_Analyzer SHALL store the estimated difficulty as `easy`, `medium`, or `hard` along with a reasoning note of no more than 200 characters for audit purposes.
5. THE PYQ_Analyzer SHALL compute `topic_importance` as `COUNT(*) GROUP BY topic_id` over the PYQ table using a deterministic SQL query — frequency counting SHALL NOT be delegated to an LLM.
6. WHEN a topic importance score does not yet exist for a topic, THE PYQ_Analyzer SHALL default to a score of 0 until the "Map & Recalculate Importance" action is explicitly triggered.
7. WHEN the "Map & Recalculate Importance" button is activated, THE PYQ_Analyzer SHALL recompute all topic importance scores and update the `topic_importance` table, completing within 10 seconds for up to 500 PYQ records.
8. WHEN the PYQ Exam Paper screen is open, THE PYQ_Analyzer SHALL display a Topic Frequency Analysis table showing: topic name, asked count, difficulty color bar (red for hard, amber for medium, green for easy), and reference weight.
9. WHEN the PYQ Exam Paper screen is open, THE PYQ_Analyzer SHALL display a Historical Question Library listing each stored PYQ with its year and difficulty badge.

---

### Requirement 12: Mock Exam Paper Assembly

**User Story:** As a student, I want to generate a mock exam paper so that I can practice under realistic exam conditions based on actual PYQ patterns.

#### Acceptance Criteria

1. WHEN a student opens the Mock Exam Paper Assembler, THE Mock_Paper_Assembler SHALL present fields for: subject selection, total marks target (positive integer), and question type distribution (e.g., 2×10mark + 4×6mark + 4×2mark).
2. WHEN "Assemble Paper" is triggered, THE Mock_Paper_Assembler SHALL select unique questions ranked by `topic_importance` in descending order, breaking ties by most recent year. IF all topic importance scores are 0, THE Mock_Paper_Assembler SHALL select questions uniformly at random.
3. WHEN assembling a paper, THE Mock_Paper_Assembler SHALL build toward the specified mark distribution. IF the total marks target is reached before the distribution is exactly satisfied, THE Mock_Paper_Assembler SHALL finalize the paper at that point.
4. IF the PYQ bank has insufficient questions to satisfy the minimum requested distribution, THEN THE Mock_Paper_Assembler SHALL assemble the paper using all available questions, display a warning indicating which question types could not be fully satisfied, and SHALL NOT abort silently.
5. WHEN a mock paper is generated, THE Mock_Paper_Assembler SHALL display the assembled questions ordered by marks descending, with each question showing its topic tag and marks allocation.

---

### Requirement 13: Spaced Repetition Flashcards

**User Story:** As a student, I want to study flashcards with spaced repetition scheduling so that I review material at optimal intervals for long-term retention.

#### Acceptance Criteria

1. WHEN a note is generated for a topic, THE Generation_Service SHALL generate 4–6 flashcards from that note's content where each card's front is a single focused question and each card's back is a concise answer under 40 words with a citation.
2. THE Generation_Service SHALL NOT create flashcard content for facts not present in the generated note.
3. THE Spaced_Repetition_Scheduler SHALL implement the SM-2 algorithm with an initial `ease_factor` of 2.5 to compute `ease_factor` and `next_review_at` for each flashcard.
4. WHEN a student completes a flashcard review, THE Spaced_Repetition_Scheduler SHALL update the card's `ease_factor` and `next_review_at` based on the student's self-reported recall score on the SM-2 integer scale of 0 to 5.
5. IF a student submits a recall score outside the range 0–5, THEN THE Spaced_Repetition_Scheduler SHALL reject the submission and prompt the student to enter a value between 0 and 5.
6. WHEN a student opens the spaced repetition screen, THE Tattva UI SHALL display the flashcard study center showing: the question front, a recall score input (0–5), a "Submit" action, the topic tag, and a "Reveal Spaced Repetition Answer" button.
7. WHEN a student opens the spaced repetition screen, THE Tattva UI SHALL display a topic dropdown filter allowing the student to review cards for a specific topic or all topics combined. The card count and due count SHALL update immediately when the filter changes.
8. WHEN a student opens the spaced repetition screen, THE Tattva UI SHALL show spaced repetition metadata: total cards in the selected deck and cards where `next_review_at <= current datetime`.
9. WHERE Phase 4 export is enabled, WHEN a student triggers flashcard export, THE Generation_Service SHALL produce an Anki-compatible CSV file with columns: front, back, source.

---

### Requirement 14: Formula Scanner

**User Story:** As a student, I want the system to extract all formulas and algorithms from my PDFs into a structured sheet so that I have a reliable reference for exam revision.

#### Acceptance Criteria

1. WHEN a student selects a subject on the Formula Sheet screen, THE Formula_Scanner SHALL extract every formula, equation, and algorithm pseudocode present in the retrieved chunks for that subject.
2. IF a formula is incomplete in the source material, THEN THE Formula_Scanner SHALL flag it as "[incomplete in source]" and SHALL NOT complete or derive the missing parts.
3. WHEN formulas are extracted, THE Formula_Scanner SHALL present them in a Markdown table with columns: Formula/Algorithm, Variables, and Source (filename and page number). IF table rendering fails, THE Formula_Scanner SHALL return the extracted formula data as a numbered list with the same three fields.
4. WHEN the "Re-Scan Textbooks" action is triggered, THE Formula_Scanner SHALL re-run extraction against the current state of the Knowledge_Store and display a visible completion notification when the scan finishes.
5. WHEN the "Export Equation Table" action is triggered, THE Formula_Scanner SHALL download the formula table as a Markdown (.md) file.
6. WHEN the formula table is rendered, THE Tattva UI SHALL display equations using LaTeX rendering (via a library such as KaTeX) so that mathematical notation is human-readable rather than raw LaTeX strings.

---

### Requirement 15: Mermaid Diagram Generation (Phase 4)

**User Story:** As a student, I want visual diagrams generated for complex topics so that I can understand processes and relationships more easily.

#### Acceptance Criteria

1. WHEN a 6-mark or 10-mark note is successfully generated, THE Generation_Service SHALL attempt to generate a Mermaid diagram representing the process or relationships described in that note.
2. IF Mermaid diagram generation fails (LLM error, invalid syntax, or render timeout), THEN THE Generation_Service SHALL still store and display the note without a diagram — the failure SHALL NOT block note storage.
3. THE Generation_Service SHALL use only concepts present in the generated note to construct the diagram and SHALL NOT introduce steps or entities not in the source text.
4. WHEN generating a diagram, THE Generation_Service SHALL select the diagram type according to these rules: use `flowchart` for processes with sequential or branching steps, `sequenceDiagram` for interactions between components or actors, and `stateDiagram` for state-transition content.
5. WHEN a valid Mermaid diagram is generated, THE Generation_Service SHALL store it in the Knowledge_Store linked to the note record.
6. WHEN a note with a stored Mermaid diagram is displayed, THE Tattva UI SHALL render the Mermaid code inline within the note display area.
7. IF the Mermaid code fails to render in the UI, THE Tattva UI SHALL display the message "Diagram unavailable — syntax error" rather than a blank or broken element.

---

### Requirement 16: Socratic Q&A Chat (Phase 4)

**User Story:** As a student, I want to ask questions about my subject material and receive grounded answers so that I can clarify doubts without relying on unverified external sources.

#### Acceptance Criteria

1. THE Socratic_Solver SHALL answer student questions using only the retrieved chunks from the student's uploaded material for the active subject (the subject selected in the current session).
2. IF the cosine similarity of the top-5 retrieved chunks against the student's question is below 0.5, THEN THE Socratic_Solver SHALL state plainly that the material does not cover the question. If a plausible module can be identified, THE Socratic_Solver SHALL name it as a suggestion — otherwise it SHALL state no relevant module was found.
3. WHEN the Socratic_Solver provides an answer to a conceptual question requiring explanation or reasoning, THE Socratic_Solver SHALL append one follow-up question of no more than 25 words to check the student's understanding.
4. IF a question is a direct lookup requiring no reasoning (e.g., "what page is X on"), THEN THE Socratic_Solver SHALL omit the follow-up question.
5. WHEN a student opens the Socratic Q&A screen, THE Tattva UI SHALL display a persistent, non-dismissible disclaimer — visible without scrolling — stating that answers are sourced only from the student's uploaded material.
6. WHEN a student opens the Socratic Q&A screen, THE Tattva UI SHALL display the active subject tag in the chat interface header, where the active subject is the one selected in the current session.

---

### Requirement 17: Export Integrations (Phase 4)

**User Story:** As a student, I want to export my notes and flashcards to external tools so that I can use them in my existing study workflow.

#### Acceptance Criteria

1. WHEN a student triggers notes export for a topic_id or module_id, THE Generation_Service SHALL produce a Markdown (.md) file containing all depth levels (2-mark, 6-mark, and 10-mark) for each requested topic.
2. WHERE Notion integration is configured, WHEN a student triggers Notion export for a topic_id or module_id, THE Generation_Service SHALL create one Notion page per topic with the topic title as the page title, containing all depth levels.
3. WHERE Obsidian integration is configured, WHEN a student triggers Obsidian export for a topic_id or module_id, THE Generation_Service SHALL write one .md file per topic named after the topic title, organized into folders by subject and module.
4. WHERE Phase 4 export is enabled, WHEN a student triggers flashcard export, THE Spaced_Repetition_Scheduler SHALL produce an Anki-compatible CSV file with columns: front, back, source.
5. IF a Notion or Obsidian export fails due to an API error or file system error, THEN THE Generation_Service SHALL abort the export, notify the student of the failure with the error type, and leave any previously exported content unchanged.

---

### Requirement 18: TTS Audio Overview (Phase 4)

**User Story:** As a student, I want an audio narration of the 6-mark note for a topic so that I can review material while away from my screen.

#### Acceptance Criteria

1. WHERE TTS integration is configured, WHEN a student requests an audio overview for a topic, THE Generation_Service SHALL narrate the 6-mark note for that topic using a text-to-speech service and produce an audio file in a browser-playable format (MP3 or OGG).
2. WHEN an audio overview is generated, THE Generation_Service SHALL cache the audio file keyed by topic_id and serve it on subsequent requests without regenerating.
3. WHEN a topic's notes are regenerated due to a content change, THE Generation_Service SHALL invalidate the cached audio file for that topic_id so the next request triggers fresh generation.
4. IF the TTS service fails to generate audio, THEN THE Generation_Service SHALL return an error to the student identifying the failure and SHALL NOT store a partial or empty audio file.

---

### Requirement 19: UI Appearance and Navigation

**User Story:** As a student, I want a consistent, focused dark-themed UI so that I can study comfortably for extended periods.

#### Acceptance Criteria

1. THE Tattva UI SHALL apply a dark theme using black and dark gray backgrounds, gold/amber accent color (#C9A84C), and white text throughout all screens.
2. THE Tattva UI SHALL display a persistent sidebar navigation with links to all six primary screens (Syllabus Coverage, Grounded Notes, PYQ Exam Paper, Spaced Repetition, Socratic Q&A, Formula Sheet) on every screen, with the active screen visually indicated.
3. THE Tattva UI SHALL be built using Next.js, Tailwind CSS, and shadcn/ui component library.
4. THE Tattva UI SHALL be responsive and usable at desktop viewport widths of 1280px and above, with all interactive controls meeting a minimum tap/click target size of 44×44 CSS pixels.

---

### Requirement 20: Parser and Serializer Round-Trip Integrity

**User Story:** As a developer, I want the parsing and serialization pipeline to be verifiably consistent so that no content is silently lost or mutated between ingestion and storage.

#### Acceptance Criteria

1. THE Parser SHALL produce structured chunk objects containing text, page number, document ID, and topic ID for every extracted text segment.
2. THE Knowledge_Store SHALL serialize chunk objects to the PostgreSQL database and deserialize them back to an equivalent in-memory structure.
3. FOR ALL valid chunk objects, serializing then deserializing SHALL produce a chunk object whose text, page number, document ID, and topic ID fields are identical to the original (round-trip property).
4. THE Generation_Service SHALL serialize generated notes to the `notes` table and deserialize them back to an equivalent Markdown structure.
5. FOR ALL valid note objects, storing then retrieving SHALL produce note content (Markdown text, confidence badge, depth, topic_id, and timestamp) identical to the stored values (round-trip property).
6. THE Tattva test suite SHALL include property-based tests that verify the round-trip properties in criteria 3 and 5 using a minimum of 100 randomly generated valid inputs per property.
