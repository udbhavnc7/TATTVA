"""
Ingestion Service router.

Endpoints:
    POST /ingest          — Accept a PDF upload, hash, deduplicate, store
    GET  /documents       — List all ingested documents
    DELETE /documents/{id} — Remove a document
"""

from fastapi import APIRouter

router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.get("/health")
async def health() -> dict:
    """Placeholder health-check for the Ingestion Service."""
    return {"service": "ingestion", "status": "ok"}
