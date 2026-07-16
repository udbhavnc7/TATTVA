"""
Parsing Service router.

Endpoints (to be implemented):
    POST /parse/{document_id} — Trigger parsing for an ingested document
"""

from fastapi import APIRouter

router = APIRouter(prefix="/parse", tags=["parsing"])


@router.get("/health")
async def health() -> dict:
    """Placeholder health-check for the Parsing Service."""
    return {"service": "parsing", "status": "ok"}
