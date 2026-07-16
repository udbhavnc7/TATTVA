"""
Tattva Exam Engine — FastAPI application entry point.

Starts the app and includes routers from all five core services:
  - Ingestion Service
  - Parsing Service
  - Classification Service
  - Knowledge Store Service
  - Generation Service
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services.classification.router import router as classification_router
from app.services.generation.router import router as generation_router
from app.services.ingestion.router import router as ingestion_router
from app.services.knowledge_store.router import router as knowledge_store_router
from app.services.parsing.router import router as parsing_router

app = FastAPI(
    title="Tattva Exam Engine",
    description=(
        "AI-powered exam preparation platform. "
        "Every generated note is grounded — every claim cites the exact source page."
    ),
    version="0.1.0",
)

# Allow the Next.js frontend (default dev port 3000) during development.
# Tighten origins for production deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register service routers ---
app.include_router(ingestion_router)
app.include_router(parsing_router)
app.include_router(classification_router)
app.include_router(knowledge_store_router)
app.include_router(generation_router)


@app.get("/", tags=["root"])
async def root() -> dict:
    """Root health-check — confirms the API is running."""
    return {"app": "Tattva Exam Engine", "status": "running", "version": "0.1.0"}
