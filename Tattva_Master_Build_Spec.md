# Tattva — Master Build Spec (Final, v3)

This merges the architecture from the first spec, the competitive refinements from v2, and adds what was missing until now: **the actual prompts** each pipeline stage runs, and **a prompt-by-prompt build sequence** you can hand to Claude Code (or Kiro) to build this phase by phase instead of staring at a blank repo.

---

## PART A — Final Architecture

```
Ingestion (Drive/Classroom OAuth watch)
        │
Parsing (PyMuPDF + fallback OCR)
        │
Classification (LLM: subject → module → topic)
        │
Diff Check (hash compare — skip if unchanged)
        │
   ┌────┴────────────────────────┐
   ▼                             ▼
Knowledge Store              PYQ Analyzer
(Postgres + pgvector,       (frequency + difficulty +
 chunked & page-tagged)      cross-paper correlation)
   │                             │
   └──────────┬──────────────────┘
              ▼
     Generation Layer (RAG-grounded, per changed topic only)
       ├─ Notes @ 2/6/10-mark depth
       ├─ Formula sheet
       ├─ Mermaid diagrams
       ├─ Flashcards (spaced repetition)
       └─ Mock-paper assembly
              │
              ▼
     Confidence Self-Check (grounded / partial / needs-review)
              │
              ▼
     Publish → notes site + notify + export (MD/Notion/Obsidian/Anki)
```

Five real services (Ingestion, Parsing, Classification+Diff, Knowledge Store, Generation) — not nine agents. PYQ Analyzer is a sixth, but it's simple and mostly deterministic.

---

## PART B — Data Model (Postgres)

```sql
subjects(id, name, code)
modules(id, subject_id, number, title)
topics(id, module_id, name, content_hash, version, last_updated)
documents(id, subject_id, source_type, source_id, filename, uploaded_at, content_hash)
chunks(id, topic_id, document_id, page_number, text, embedding vector(1536))
notes(id, topic_id, version, depth /* '2mark'|'6mark'|'10mark' */, content_md, confidence /* grounded|partial|review */, generated_at)
pyqs(id, subject_id, year, question_text, topic_id, marks, difficulty)
topic_importance(topic_id, frequency_count, difficulty_avg, last_recalculated)
flashcards(id, topic_id, question, answer, ease_factor, next_review_at)
```

Every `chunks` row keeps `document_id` + `page_number` — this is what makes citations possible later. Don't collapse this into a single blob field.

---

## PART C — Stage-by-Stage: The Actual Prompts

Each of these is a real system/user prompt template you drop into the Generation Layer. `{{placeholders}}` get filled at call time.

### C1. Classification Prompt
```
SYSTEM:
You classify academic PDF content into a subject/module/topic taxonomy.
You will be given the existing taxonomy for this student's course and the
extracted headings/text of a new document. Output ONLY valid JSON, no
preamble.

Rules:
- Match to an EXISTING subject/module if it clearly fits.
- Only propose a NEW module/topic if nothing existing fits — do not
  silently merge distinct topics to avoid creating a new entry.
- If uncertain, set "confidence": "low" and explain why in "note".

Existing taxonomy:
{{existing_taxonomy_json}}

Document headings/content sample:
{{extracted_headings}}

Output schema:
{
  "subject": string,
  "module_number": integer,
  "topic": string,
  "is_new_topic": boolean,
  "confidence": "high" | "medium" | "low",
  "note": string
}
```

### C2. Note Generation Prompt (the core one — grounded, depth-tiered)
```
SYSTEM:
You write exam-focused study notes for an engineering student. You must
use ONLY the retrieved context below — do not add facts from your own
training data. Every factual claim must be traceable to a chunk in the
context. If the context doesn't cover something needed at this depth,
say "Not covered in provided material" instead of filling the gap.

Depth level for this generation: {{depth}}   // "2mark" | "6mark" | "10mark"

Depth instructions:
- 2mark: a crisp definition/answer, 2-4 sentences max.
- 6mark: definition + explanation + one example or diagram reference.
- 10mark: full explanation, all sub-points, at least one diagram
  reference, advantages/disadvantages or comparison if applicable.

For every paragraph, append a citation in the form:
  (Source: {{document_filename}}, p.{{page_number}})

Retrieved context (chunks, each tagged with source + page):
{{retrieved_chunks}}

Topic: {{topic_name}}
Module: {{module_number}} — {{subject_name}}

Output the notes in Markdown. End with a line:
CONFIDENCE: grounded | partial | needs_review
(grounded = every claim cited and directly supported;
 partial = some claims inferred/combined across chunks but still
 source-consistent; needs_review = context was thin or ambiguous)
```

### C3. Diagram Generation Prompt
```
SYSTEM:
Generate a Mermaid diagram (flowchart, sequence, or state diagram —
choose the type that fits) that visually represents the process or
relationship described below. Use ONLY the concepts present in the
provided notes — do not invent steps that aren't in the source text.
Keep node labels short (under 6 words).

Source notes for this topic:
{{generated_note_text}}

Output ONLY the Mermaid code block, nothing else.
```

### C4. Formula Sheet Extraction Prompt
```
SYSTEM:
Extract every formula, equation, or algorithm pseudocode present in the
context below. Do not derive or complete partial formulas — if a formula
is incomplete in the source, flag it as "[incomplete in source]" rather
than finishing it yourself.

Context:
{{retrieved_chunks}}

Output as a Markdown table: | Formula/Algorithm | Variables | Source (file, page) |
```

### C5. PYQ Topic-Matching Prompt
```
SYSTEM:
Match the following exam question to ONE topic from the taxonomy below.
If it spans multiple topics, pick the primary one and list secondary
topics separately. Output JSON only.

Taxonomy: {{topic_list}}
Question: {{pyq_text}}
Marks allotted: {{marks}}
Year: {{year}}

Output:
{
  "primary_topic": string,
  "secondary_topics": [string],
  "estimated_difficulty": "easy" | "medium" | "hard",
  "reasoning": string   // one sentence, for audit purposes only
}
```
Note: frequency counting itself is NOT done by the LLM — it's a deterministic
`COUNT(*) GROUP BY topic_id` over this table. Only the matching step uses
the model. This keeps the "asked 6 times" number impossible to hallucinate.

### C6. Flashcard Generation Prompt
```
SYSTEM:
Generate 4-6 spaced-repetition flashcards from the notes below. Each card:
front = a single focused question, back = a concise answer (under 40 words)
with a citation. Do not create cards for facts not present in the notes.

Notes:
{{generated_note_text}}

Output as JSON array: [{"front": "...", "back": "...", "source": "..."}]
```

### C7. Guided Doubt-Solver Prompt
```
SYSTEM:
You are a study assistant answering ONLY from this student's own course
material (retrieved below). If the material doesn't cover the question,
say so plainly and suggest which module might be relevant instead of
guessing. After answering, ask ONE short follow-up question to check the
student actually understood the concept (Socratic check) — skip this if
the question was purely factual (e.g., "what page is X on").

Retrieved context:
{{retrieved_chunks}}

Student question:
{{user_question}}
```

### C8. Post-Generation Confidence Validator (a second pass, cheap model)
```
SYSTEM:
Review the generated note below against its cited source chunks. Flag any
sentence that is NOT directly supported by the cited chunk as
"UNSUPPORTED". Output a list of unsupported sentences (empty list if none).
This is a safety check, not a rewrite — do not fix the note yourself.

Generated note:
{{generated_note_text}}

Cited chunks:
{{retrieved_chunks}}

Output: {"unsupported_sentences": [string]}
```
If this returns any unsupported sentences, the note's confidence badge
gets downgraded to `needs_review` regardless of what C2 self-reported.
This is the one place worth spending a second LLM call — it's your actual
hallucination guardrail, not just a prompt instruction hoping the model
behaves.

---

## PART D — Build Sequence: Prompt-by-Prompt for Your Coding Agent

Use these as literal prompts to Claude Code/Kiro, in order. Each assumes the
previous one is done and tested before moving on. Don't batch them — verify
each stage works on a real PDF before building the next.

### Phase 1 — Core Loop (prove it works, no Classroom yet)

**Prompt 1:**
> Set up a FastAPI project called `tattva-core` with Postgres + pgvector via
> docker-compose. Create the schema from [paste Part B schema]. Add a single
> endpoint `POST /ingest` that accepts a PDF file upload, stores it, and
> returns a document_id.

**Prompt 2:**
> Add PDF parsing to `tattva-core` using PyMuPDF. Extract headings, body
> text, and detect image-only pages (for later OCR). Store extracted text
> chunks in the `chunks` table, unembedded for now. Write a test using a
> sample PDF.

**Prompt 3:**
> Add an embeddings step: chunk the extracted text (~500 tokens per chunk,
> preserve page numbers), call an embedding model, store vectors in
> `chunks.embedding`. Add a `GET /search?q=` endpoint that does a pgvector
> similarity search and returns matching chunks with their source page.

**Prompt 4:**
> Implement the classification stage using this exact prompt: [paste C1].
> Add `POST /classify` that takes a document_id, runs the parsed headings
> through this prompt, and writes subject/module/topic rows if they don't
> exist.

**Prompt 5:**
> Implement note generation using this exact prompt: [paste C2]. Add
> `POST /generate-notes` that takes a topic_id and depth level, retrieves
> the top-k relevant chunks for that topic from pgvector, runs the prompt,
> and stores the result in the `notes` table with its confidence badge.

**Prompt 6:**
> Implement the confidence validator from this prompt: [paste C8]. Run it
> automatically after every note generation and downgrade the confidence
> badge if it flags unsupported sentences. Log flagged sentences for review.

**Prompt 7:**
> Build a minimal Next.js frontend that lists subjects → modules → topics,
> shows generated notes with their confidence badge and citations visible
> on hover, and has an "upload PDF" button hitting `/ingest`.

At the end of Phase 1 you have a fully working, manually-fed, grounded
note generator. This alone is demoable.

### Phase 2 — Make It Live

**Prompt 8:**
> Add Google OAuth2 and Drive API integration to `tattva-core`. Implement
> a `watch` channel on a specified Drive folder that triggers `/ingest`
> automatically when a new file appears.

**Prompt 9:**
> Implement the content-hash diff check described in Part B: before
> reprocessing a topic, compare `content_hash` against the stored value.
> Skip regeneration if unchanged. Add a `version` bump and history table
> entry if changed.

**Prompt 10:**
> Implement flashcard generation using this prompt: [paste C6]. Add a
> simple spaced-repetition scheduler (SM-2 algorithm is fine) updating
> `ease_factor` and `next_review_at` on each review.

**Prompt 11:**
> Add export endpoints: notes → Markdown file, → Notion (via Notion API),
> → Obsidian-compatible folder structure, flashcards → Anki-compatible CSV.

### Phase 3 — The Differentiators

**Prompt 12:**
> Add a `pyqs` ingestion path (PDF upload of past question papers) and
> implement topic matching using this prompt: [paste C5]. Compute
> `topic_importance` via a deterministic SQL aggregation, not an LLM call.

**Prompt 13:**
> Build a "mock paper" assembly feature: given a subject and target total
> marks, select PYQ-style questions weighted by `topic_importance`,
> respecting the module's real mark distribution (e.g., 2×10mark +
> 4×6mark + 4×2mark).

**Prompt 14:**
> Add a syllabus coverage tracker: percentage of topics per module that
> have a "grounded" or "partial" note versus "needs_review" or missing.

### Phase 4 — Stretch Polish

**Prompt 15:**
> Add the diagram generation prompt [paste C3] as a post-processing step
> on any 6mark/10mark note, rendering the returned Mermaid code inline in
> the frontend.

**Prompt 16:**
> Add the guided doubt-solver using prompt [paste C7] as a chat endpoint
> scoped to a subject's retrieved chunks only.

**Prompt 17 (optional):**
> Add an audio overview: TTS-narrate the 6mark note for a topic, cache the
> audio file, serve it from the topic page.

---

## PART E — Testing Checklist Before You Trust Any of This for Exam Prep

- [ ] Upload a PDF you already know cold. Check every generated claim against the source page manually — this is your ground truth calibration, do it before trusting it on unfamiliar material.
- [ ] Deliberately upload a PDF with a partially cut-off/garbled page (OCR stress test) — confirm it flags `needs_review` rather than confidently inventing the missing part.
- [ ] Upload two versions of the same module (v1, then v1 + one new section) — confirm only the new topic regenerates, not the whole module.
- [ ] Check that PYQ frequency counts match a manual count you do by hand on a small sample.
- [ ] Confirm the confidence validator (C8) actually catches at least one deliberately-inserted unsupported sentence in a test note.

---

## Final Note

This is now genuinely buildable start-to-finish from this document — every
prompt is copy-paste ready, the schema is concrete, and the phase order is
front-loaded with what proves the concept fastest. The one thing no
document can do for you: actually running Prompt 1 in Claude Code and
seeing what breaks. Start there.
