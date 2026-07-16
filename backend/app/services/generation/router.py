"""
Generation Service router.

Endpoints (to be implemented):
    POST /generate-notes              — Generate a grounded note for topic + depth
    GET  /notes/{topic_id}            — Get all notes for a topic
    POST /topics/{id}/regenerate      — Force-regenerate (bypasses hash check)
    GET  /coverage                    — Coverage stats for dashboard
"""

from fastapi import APIRouter

router = APIRouter(prefix="/generate", tags=["generation"])


@router.get("/health")
async def health() -> dict:
    """Placeholder health-check for the Generation Service."""
    return {"service": "generation", "status": "ok"}
