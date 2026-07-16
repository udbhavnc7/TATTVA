"""
Knowledge Store router.

Endpoints (to be implemented):
    POST   /subjects                  — Create a subject
    GET    /subjects                  — List subjects
    POST   /subjects/{id}/modules     — Create a module
    GET    /subjects/{id}/modules     — List modules for a subject
    GET    /topics/{topic_id}         — Get topic details
    GET    /search                    — Semantic chunk search (?q=&k=&topic_id=)
"""

from fastapi import APIRouter

router = APIRouter(prefix="/knowledge", tags=["knowledge_store"])


@router.get("/health")
async def health() -> dict:
    """Placeholder health-check for the Knowledge Store Service."""
    return {"service": "knowledge_store", "status": "ok"}
