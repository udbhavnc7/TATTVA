"""
Classification Service router.

Endpoints (to be implemented):
    POST /classify/{document_id} — Run LLM taxonomy classification for a document
"""

from fastapi import APIRouter

router = APIRouter(prefix="/classify", tags=["classification"])


@router.get("/health")
async def health() -> dict:
    """Placeholder health-check for the Classification Service."""
    return {"service": "classification", "status": "ok"}
