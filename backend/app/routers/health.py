from fastapi import APIRouter, Response
from sqlalchemy import text

from ..database import SessionLocal
from ..jobs import job_manager
from ..services.llm import ollama_status

router = APIRouter(prefix="/api/health", tags=["health"])


async def _db_ok() -> bool:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/live")
async def live():
    """Liveness: the process is up and serving requests."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response):
    """Readiness: the database is reachable (the LLM is reported but not required)."""
    db = await _db_ok()
    if not db:
        response.status_code = 503
    return {"status": "ok" if db else "unavailable", "database": db}


@router.get("")
async def health():
    """Full status for the UI: database, LLM server and job queue."""
    db = await _db_ok()
    llm = await ollama_status()
    ok = db and llm["reachable"] and llm["model_available"]
    return {"status": "ok" if ok else "degraded", "database": db, "llm": llm, "jobs": job_manager.stats()}
