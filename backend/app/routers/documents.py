import logging
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..jobs import job_manager
from ..models import Document
from ..schemas import DocumentOut, DocumentSummary, DocumentUpdate, document_out, document_summary
from ..services import export

router = APIRouter(prefix="/api/documents", tags=["documents"])
log = logging.getLogger("docformatter.api.documents")


async def _get_or_404(session: AsyncSession, doc_id: int) -> Document:
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("", response_model=list[DocumentSummary])
async def list_documents(
    q: str = Query("", max_length=200),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Document).order_by(Document.updated_at.desc()).limit(limit).offset(offset)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Document.title.ilike(like), Document.source_filename.ilike(like)))
    docs = (await session.scalars(stmt)).unique().all()
    return [document_summary(d) for d in docs]


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    return document_out(await _get_or_404(session, doc_id))


@router.put("/{doc_id}", response_model=DocumentOut)
async def update_document(doc_id: int, body: DocumentUpdate, session: AsyncSession = Depends(get_session)):
    doc = await _get_or_404(session, doc_id)
    if job_manager.is_active(doc_id) and body.formatted_markdown is not None:
        raise HTTPException(409, "The document is being formatted; wait for it to finish before editing.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(doc, key, value)
    await session.commit()
    await session.refresh(doc)
    return document_out(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await _get_or_404(session, doc_id)
    job_manager.cancel(doc_id)
    await session.delete(doc)
    await session.commit()
    log.info("document deleted", extra={"document_id": doc_id})


EXPORT_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


@router.get("/{doc_id}/export")
async def export_document(
    doc_id: int,
    format: Literal["md", "html", "docx", "pdf"] = "md",
    session: AsyncSession = Depends(get_session),
):
    doc = await _get_or_404(session, doc_id)
    md = doc.formatted_markdown or ""
    if not md.strip():
        raise HTTPException(400, "Document has no formatted content to export.")

    if format == "md":
        content: bytes = md.encode("utf-8")
    elif format == "html":
        content = export.markdown_to_html(md, doc.title).encode("utf-8")
    elif format == "docx":
        content = await run_in_threadpool(export.markdown_to_docx, md, doc.title)
    else:
        content = await run_in_threadpool(export.markdown_to_pdf, md, doc.title)

    filename = export.safe_filename(doc.title, format)
    return Response(
        content,
        media_type=EXPORT_TYPES[format],
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            # Exported HTML must never execute in the app's origin
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "no-store",
        },
    )
