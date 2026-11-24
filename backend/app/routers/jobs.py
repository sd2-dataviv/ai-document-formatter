import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_session
from ..jobs import END, Job, job_manager, provisional_title, terminal_event
from ..models import STATUS_QUEUED, Document, Template
from ..schemas import FormatRequest, JobCreated, document_out

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
log = logging.getLogger("docformatter.api.jobs")

KEEPALIVE_SECONDS = 15
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _encode(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, default=str) + "\n").encode("utf-8")


@router.post("", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_job(req: FormatRequest, session: AsyncSession = Depends(get_session)):
    """Queue a formatting job. Progress is streamed from GET /api/jobs/{document_id}/events."""
    settings = get_settings()
    if not req.text.strip():
        raise HTTPException(422, "Text is empty.")
    if len(req.text) > settings.max_input_chars:
        raise HTTPException(413, f"Text exceeds the {settings.max_input_chars:,} character limit.")
    if job_manager.active_count() >= settings.max_queued_jobs:
        raise HTTPException(429, "The formatter queue is full. Please try again in a few minutes.")

    template: Template | None = None
    if req.template_id is not None:
        template = await session.get(Template, req.template_id)
        if template is None:
            raise HTTPException(404, "Template not found")

    if req.document_id is not None:
        doc = await session.get(Document, req.document_id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        if job_manager.is_active(doc.id):
            raise HTTPException(409, "This document is already being formatted.")
        doc.title = req.title.strip()[:255] or doc.title
    else:
        doc = Document(title=provisional_title(req))
        session.add(doc)

    doc.source_filename = req.source_filename
    doc.original_text = req.text
    doc.template_id = template.id if template else None
    doc.custom_instructions = req.custom_instructions
    doc.model = settings.ollama_model
    doc.think_level = req.think_level
    doc.status = STATUS_QUEUED
    doc.error = None
    await session.commit()

    # Re-check after the await: another request may have started a job for this document.
    if job_manager.is_active(doc.id):
        raise HTTPException(409, "This document is already being formatted.")
    job = job_manager.submit(
        Job(document_id=doc.id, request=req, template_instructions=template.instructions if template else None)
    )
    log.info("job queued", extra={"document_id": doc.id})
    return JobCreated(document_id=doc.id, status=job.status, queue_position=job.queue_position)


@router.get("/{document_id}/events")
async def job_events(document_id: int, session: AsyncSession = Depends(get_session)):
    """NDJSON stream: a `snapshot` of progress so far, then live events until a terminal event.

    Terminal events are `done`, `error` and `cancelled`; `ping` is sent periodically as a keep-alive.
    Disconnecting does not stop the job, and reconnecting resumes from a fresh snapshot.
    """
    doc = await session.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")

    q = job_manager.subscribe(document_id)
    if q is None:
        # No live job in this process: replay the stored final state.
        snapshot = {
            "type": "snapshot",
            "status": doc.status,
            "queue_position": 0,
            "chunk": None,
            "markdown": doc.formatted_markdown,
            "thinking": "",
        }
        error = doc.error or ("The job is no longer running." if doc.status == STATUS_QUEUED else None)
        final = terminal_event(doc.status, document_out(doc), error)

        async def replay() -> AsyncIterator[bytes]:
            yield _encode(snapshot)
            yield _encode(final)

        return StreamingResponse(replay(), media_type="application/x-ndjson", headers=STREAM_HEADERS)

    async def stream() -> AsyncIterator[bytes]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield _encode({"type": "ping"})
                    continue
                if event is END:
                    break
                yield _encode(event)
        finally:
            job_manager.unsubscribe(document_id, q)

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers=STREAM_HEADERS)


@router.post("/{document_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_job(document_id: int):
    if not job_manager.cancel(document_id):
        raise HTTPException(409, "No running job for this document.")
    log.info("job cancel requested", extra={"document_id": document_id})
    return {"status": "cancelling"}


@router.get("/stats")
async def job_stats():
    return job_manager.stats()
