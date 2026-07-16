# Tattva — Autonomous Syllabus Intelligence Agent

*"Tattva" (तत्त्व) — essence, the fundamental nature of a thing. Fitting: the agent's whole job is to distill lecture material down to its essence.*

---

## 1. The One-Line Pitch

Tattva watches your Google Classroom/Drive, reads every new PDF the moment it lands, and keeps a living, syllabus-aligned notes site up to date — incrementally, with every claim traceable back to the exact page it came from, and a PYQ-driven "what's actually going to be asked" layer on top.

That last clause — **source-grounded + PYQ-weighted** — is the differentiator. Most "AI notes" tools just summarize. Tattva tells you *why* a topic matters and *where* the claim came from.

---

## 2. Reality Check — What Was Wrong or Fragile in the Original Plan

I'm listing these up front because pretending they don't exist is how these projects break in week 3, not because the idea is bad.

| Issue in original draft | Why it matters | Fix in this version |
|---|---|---|
| 9 "agents" for what is really 4-5 pipeline stages | Over-decomposition = more inter-agent glue code, more failure points, harder to debug | Collapsed to 5 real services (§4) |
| No hallucination control | An LLM "explaining Deadlock" from memory instead of your PDF will confidently invent wrong content — dangerous for exam prep | Mandatory retrieval-grounded generation + citation-or-refuse rule (§6) |
| "Update only affected sections" stated but no mechanism | Without a diffing strategy this either re-runs everything (expensive) or silently misses updates (worse) | Content-hash based incremental pipeline (§5) |
| Google Classroom API access glossed over | This is the single biggest real-world risk to the whole project | Concrete, honest integration path (§8) |
| No cost model | GPT-5.5/Gemini calls on every PDF, every module, every depth-level (2/6/10 marks) adds up fast for a student budget | Cost estimate + caching strategy (§9) |
| Diagram generation via raw SVG | LLM-generated SVG is unreliable (broken paths, overlaps) | Mermaid-first, SVG only as a fallback render target (§7) |
| No eval/quality-control loop | "Trust the LLM's notes for your board exam" is a real risk | Confidence scoring + human-in-loop review flag (§6, §10) |
| No phasing | Building all 9 agents before validating any of them is how side projects die | 3-phase MVP roadmap (§11) |

None of this kills the idea. It just means "ultimate agent, zero flaws" becomes "well-engineered agent with known, mitigated risks" — which is the honest and, frankly, more impressive version to put on a resume.

---

## 3. What Tattva Actually Does (End-to-End)

```
New PDF appears in Classroom/Drive
        │
        ▼
1. Ingest      → download, hash, dedupe, store raw file
        │
        ▼
2. Parse       → extract text/headings/formulas/tables/images
                  (PyMuPDF first, OCR only on image-only pages)
        │
        ▼
3. Classify    → subject → module → topic (LLM + rule-based fallback)
        │
        ▼
4. Diff        → compare parsed content hash against last known
                  version of that topic → only changed topics proceed
        │
        ▼
5. Ground      → chunk + embed → upsert into pgvector, tagged by
                  subject/module/topic/source-page
        │
        ▼
6. Generate    → RAG-grounded notes at 3 depths (2/6/10 marks),
                  formula sheet, memory aids, Mermaid diagrams
        │
        ▼
7. PYQ Weight  → cross-reference topic against PYQ corpus →
                  frequency score → "importance" tag
        │
        ▼
8. Publish     → write to notes site, log diff/version, notify you
```

Steps 1-5 are deterministic/cheap. Step 6 is the only expensive LLM-heavy step, and thanks to step 4 it only runs on what actually changed.

---

## 4. Services (Not 9 Agents — 5 Real Components)

**A. Ingestion Service**
Polls Classroom/Drive on a schedule (or webhook where available), downloads new/changed files, computes a content hash, stores metadata in Postgres. Nothing clever here — this is the part that must never silently fail, so it gets the most defensive error handling and retry logic.

**B. Parsing & Structuring Service**
PyMuPDF/pdfplumber for text-native PDFs. Falls back to OCR (Tesseract or a vision-capable LLM call) only for scanned/image pages — this is a real cost lever, don't OCR everything by default.
Extracts: headings, definitions, formulas (→ LaTeX), tables, figure regions, example problems.

**C. Knowledge Store**
- Postgres: subjects, modules, topics, documents, versions, questions, notes, metadata
- pgvector: chunk embeddings tagged with `(subject, module, topic, source_doc_id, page_number)`
- This tagging is what makes citations possible later — don't skip it to save schema complexity.

**D. Reasoning & Generation Service**
This is where the LLM lives. Every generation call is **RAG-grounded**: it retrieves the relevant chunks from pgvector for that topic and is instructed to answer *only* from retrieved context, citing page numbers, and to explicitly say "not covered in provided material" rather than filling gaps from its own training data. This single rule is the difference between a study aid and a liability.

**E. PYQ Analyzer**
Separate, simpler service — mostly retrieval + frequency counting, not heavy generation. Topic extraction from PYQs, fuzzy-matched against your topic taxonomy, frequency → star rating. Cheap, deterministic, high value. Build this early (see roadmap).

Diagram generation and the "revision compressor" and "doubt solver" from the original draft aren't separate agents — they're just different *prompts* against the same Reasoning Service, using the same grounded context. No need to over-architect them.

---

## 5. Incremental Update Logic (the part the original draft skipped)

```
For each parsed topic block:
    new_hash = hash(normalized_text)
    if topic_id exists in DB:
        if new_hash == stored_hash:
            skip — nothing changed
        else:
            mark topic as "changed"
            increment version
            re-run steps 5-8 for THIS TOPIC ONLY
    else:
        new topic → run full pipeline
```

Store every version (don't overwrite). This gives you version history for free (one of the "nice to have" features in the original draft) and lets you roll back if a generation goes wrong.

---

## 6. Anti-Hallucination Rules (non-negotiable for an exam-prep tool)

1. Every generated note block must carry a citation: `(Source: OS_Module4.pdf, p.12)`.
2. Generation prompt explicitly forbids adding facts not present in retrieved chunks.
3. If retrieval confidence is low (e.g., low cosine similarity across top-k chunks), the system flags the topic as "low confidence — needs review" instead of generating anyway.
4. You (or any user) can see a confidence badge per note section: Grounded / Partially Grounded / Needs Review.
5. PYQ importance scores are counts, not LLM guesses — keep this deterministic so it can't hallucinate a fake "asked 6 times."

---

## 7. Diagrams

Use **Mermaid** as the primary target — it's structured text, so the LLM generates something with a much higher success rate than free-form SVG, and it renders natively in most markdown/web stacks. Reserve raw SVG only for cases Mermaid can't express (e.g., annotated physical diagrams), and even then, generate from a constrained template rather than freehand.

---

## 8. Google Classroom / Drive Integration — the Honest Version

There's no public API that lets an arbitrary third-party app read anyone's Classroom materials. What you *can* do, realistically, for your own account:

- Use the **Google Classroom API** (`classroom.courses.get`, `classroom.courseWork.get`, `classroom.announcements.get`) with OAuth2, scoped to courses **you** are enrolled in and have granted access to via your own Google Cloud project.
- Materials often live in **Google Drive** (linked from Classroom posts) — the **Drive API** with a push notification (`watch`) channel is more reliable for detecting new files than polling Classroom directly.
- Practical MVP: OAuth once, poll the specific Drive folder(s) your lecturers post into (or the Drive files attached to Classroom posts) every N minutes, rather than trying to build a generic multi-user Classroom scraper.
- Do **not** design this to access anyone else's classroom data or bypass permission scopes — it needs to be your own OAuth-consented access only.

This is the part of the project most likely to have a rough edge (Google's UI/permission changes, rate limits) — build the rest of the pipeline against a local "drop a PDF in this folder" mode first, so Classroom/Drive is a pluggable ingestion source, not a hard dependency for demoing the rest of the system.

---

## 9. Cost & Scale Reality

Rough shape (adjust to actual pricing at build time):
- Parsing/OCR: cheap, mostly local compute.
- Embeddings: cheap, batch these.
- Generation: the real cost — 3 depth-levels × diagrams × formula sheets × PYQ cross-ref, **per changed topic**. This is exactly why the diff/incremental logic in §5 isn't optional — without it, cost scales with total syllabus size instead of "what changed today," which for a student project could mean re-generating your entire subject every time one PDF is uploaded.
- Cache aggressively: if a topic hasn't changed, never regenerate it, even on request — serve stored notes.
- Given you've already worked with the Gemini API in Vaakya and VORTEX, that's a reasonable default for the generation layer, with a cheaper/faster model reserved for classification and PYQ matching (those don't need your strongest model).

---

## 10. Quality Control Loop

- Every generated note batch gets a confidence badge (§6).
- A lightweight "flag this note" action feeds back into a review queue — you (or classmates, if this becomes multi-user later) can correct hallucinated or misclassified content, and corrections should be stored so the same mistake isn't regenerated identically next time.
- Track a simple internal metric: % of generated topics marked "Grounded" vs "Needs Review" over time — this is also a good thing to point to in a portfolio/demo.

---

## 11. Build Roadmap (Phased, Not All-At-Once)

**Phase 1 — Prove the core loop (1-2 weeks)**
Manual PDF drop → parse → classify → grounded note generation (2/6/10 marks) → citations. No Classroom integration yet. This alone is a demoable product.

**Phase 2 — Make it live**
Drive polling ingestion, incremental diffing, version history, notification (even just an email/WhatsApp ping).

**Phase 3 — The differentiators**
PYQ analyzer + importance scoring, revision compressor, quiz/flashcard generation, syllabus coverage tracker, natural-language search over your own notes.

Diagram generation and the doubt-solver chat interface can slot in anywhere in Phase 2/3 depending on what you want to demo first.

---

## 12. Tech Stack (Final)

- **Frontend:** Next.js, Tailwind, shadcn/ui
- **Backend:** FastAPI (Python) — consistent with your existing stack from VORTEX/PRISM
- **Scheduler:** APScheduler or a simple cron for MVP; Celery + Redis once you need real background job reliability (you already have this pattern from VORTEX)
- **Database:** PostgreSQL + pgvector
- **Parsing:** PyMuPDF, pdfplumber, Tesseract OCR (fallback only)
- **LLM:** Gemini API for generation; a smaller/cheaper model for classification and PYQ matching
- **Diagrams:** Mermaid (primary), SVG (fallback)
- **Auth/Ingestion:** Google OAuth2 + Drive API (push notifications where possible)

---

## 13. What Would Make This Genuinely Portfolio-Strong

Not "add more agents" — the strong signal for reviewers is:
1. You can explain *why* the grounding/citation design exists (shows you understand LLM failure modes, not just LLM plumbing).
2. The incremental-diff system works and you can demo it live (upload one PDF, show only one topic regenerates).
3. You have a confidence/review metric, however simple — shows product thinking, not just "wired an API to a UI."

That's a much stronger story than a 9-agent diagram, and it's also less work to actually finish.

---

## Open Question for You

Do you want Phase 1 scoped as: (a) a real working prototype you start coding now, or (b) a polished spec/pitch doc for a hackathon submission first? The engineering priorities shift a bit depending on which — a hackathon needs a working demo of the *coolest* part (PYQ weighting + grounded generation) fast; a real personal tool needs the ingestion pipeline solid first since that's what runs unattended.
