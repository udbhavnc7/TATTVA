# Tattva Exam Engine — Backend

FastAPI backend for the Tattva AI-powered exam preparation platform.

## Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/) for dependency management
- PostgreSQL 15+ with the `pgvector` extension

## Setup

```bash
# 1. Install dependencies
poetry install

# 2. Copy and fill in environment variables
cp .env.example .env

# 3. Run database migrations
poetry run alembic upgrade head

# 4. Start the development server
poetry run uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

## Project structure

```
backend/
├── app/
│   ├── main.py                       # FastAPI app, router registration
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                   # SQLAlchemy DeclarativeBase
│   │   └── session.py                # Async engine + session factory
│   └── services/
│       ├── ingestion/
│       │   ├── __init__.py
│       │   └── router.py             # POST /ingest, GET/DELETE /documents
│       ├── parsing/
│       │   ├── __init__.py
│       │   └── router.py             # POST /parse/{document_id}
│       ├── classification/
│       │   ├── __init__.py
│       │   └── router.py             # POST /classify/{document_id}
│       ├── knowledge_store/
│       │   ├── __init__.py
│       │   └── router.py             # GET /search, /subjects, /topics
│       └── generation/
│           ├── __init__.py
│           └── router.py             # POST /generate-notes, GET /notes
├── alembic/                          # Migration scripts (populated by alembic)
├── alembic.ini
├── pyproject.toml
├── .env.example
└── README.md
```

## Services

| Service | Prefix | Responsibility |
|---|---|---|
| Ingestion | `/ingest` | File receipt, SHA-256 dedup, Drive polling |
| Parsing | `/parse` | PyMuPDF extraction, OCR fallback, chunking |
| Classification | `/classify` | LLM taxonomy mapping, confidence flagging |
| Knowledge Store | `/knowledge` | PostgreSQL + pgvector CRUD, semantic search |
| Generation | `/generate` | RAG-grounded note generation, confidence badges |
