"""In-process background jobs for LLM formatting runs.

Jobs run as asyncio tasks, decoupled from the HTTP request that created them: a client can
disconnect, reconnect and receive a snapshot of progress followed by live events. A semaphore
bounds how many jobs hit the LLM at once (the GPU is the bottleneck); the rest wait in a FIFO
queue and receive position updates.

State lives in this process, so run the API with a single worker. Scaling out horizontally
would require moving the queue and event fan-out to an external broker (e.g. Redis).
"""

import asyncio
import contextlib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import update

from .config import get_settings
from .database import SessionLocal
from .models import (
    ACTIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    Document,
)
from .schemas import FormatRequest, document_out
from .services.llm import LLMError, clean_output, split_into_chunks, stream_chat
from .services.prompts import SYSTEM_PROMPT, build_user_prompt

log = logging.getLogger("docformatter.jobs")

END = object()  # sentinel marking the end of a subscriber's event stream
RETAIN_FINISHED_SECONDS = 120  # keep finished jobs briefly so late subscribers get the final event
MAX_THINKING_CHARS = 200_000


def provisional_title(req: FormatRequest) -> str:
    if req.title.strip():
        return req.title.strip()[:255]
    if req.source_filename:
        return Path(req.source_filename).stem[:255] or "Untitled"
    first = next((ln.strip() for ln in req.text.splitlines() if ln.strip()), "Untitled")
    return (first[:80] + "…") if len(first) > 80 else first


def title_from_markdown(markdown: str) -> str | None:
    if m := re.search(r"^#\s+(.+)$", markdown, re.MULTILINE):
        title = re.sub(r"[*_`]", "", m.group(1)).strip()
        return title[:255] or None
    return None


def terminal_event(status: str, document: dict[str, Any] | None, error: str | None) -> dict[str, Any]:
    if status == STATUS_COMPLETED:
        return {"type": "done", "document": document}
    if status == STATUS_CANCELLED:
        return {"type": "cancelled", "document": document}
    return {"type": "error", "message": error or "Formatting failed.", "document": document}


@dataclass(eq=False)
class Job:
    document_id: int
    request: FormatRequest
    template_instructions: str | None
    status: str = STATUS_QUEUED
    markdown: str = ""
    thinking: str = ""
    chunk: dict[str, int] | None = None
    queue_position: int = 0
    final_event: dict[str, Any] | None = None
    started_at: float = field(default_factory=time.perf_counter)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    task: asyncio.Task | None = None

    @property
    def active(self) -> bool:
        return self.final_event is None

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "status": self.status,
            "queue_position": self.queue_position,
            "chunk": self.chunk,
            "markdown": self.markdown,
            "thinking": self.thinking,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._waiting: list[Job] = []
        self._sem: asyncio.Semaphore | None = None
        self._shutting_down = False

    # ------------------------------------------------------------------ lifecycle

    def start(self, max_concurrent: int) -> None:
        self._sem = asyncio.Semaphore(max(1, max_concurrent))
        self._jobs.clear()
        self._waiting.clear()
        self._shutting_down = False

    async def shutdown(self) -> None:
        self._shutting_down = True
        tasks = [j.task for j in self._jobs.values() if j.task and not j.task.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=10)

    # ------------------------------------------------------------------ queries

    def get(self, document_id: int) -> Job | None:
        return self._jobs.get(document_id)

    def is_active(self, document_id: int) -> bool:
        job = self._jobs.get(document_id)
        return bool(job and job.active)

    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.active)

    def stats(self) -> dict[str, int]:
        active = [j for j in self._jobs.values() if j.active]
        return {
            "running": sum(1 for j in active if j.status == STATUS_PROCESSING),
            "queued": len(self._waiting),
        }

    # ------------------------------------------------------------------ commands

    def submit(self, job: Job) -> Job:
        if self._sem is None:
            raise RuntimeError("JobManager.start() has not been called")
        self._jobs[job.document_id] = job
        self._waiting.append(job)
        self._update_positions()
        job.task = asyncio.create_task(self._run(job), name=f"format-doc-{job.document_id}")
        return job

    def cancel(self, document_id: int) -> bool:
        job = self._jobs.get(document_id)
        if not job or not job.active or not job.task:
            return False
        job.task.cancel()
        return True

    def subscribe(self, document_id: int) -> asyncio.Queue | None:
        job = self._jobs.get(document_id)
        if job is None:
            return None
        q: asyncio.Queue = asyncio.Queue()
        q.put_nowait(job.snapshot())
        if job.final_event is not None:
            q.put_nowait(job.final_event)
            q.put_nowait(END)
        else:
            job.subscribers.add(q)
        return q

    def unsubscribe(self, document_id: int, q: asyncio.Queue) -> None:
        if job := self._jobs.get(document_id):
            job.subscribers.discard(q)

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _emit(job: Job, event: Any) -> None:
        for q in list(job.subscribers):
            q.put_nowait(event)

    def _append(self, job: Job, kind: str, text: str) -> None:
        if kind == "content":
            job.markdown += text
        elif len(job.thinking) < MAX_THINKING_CHARS:
            job.thinking += text
        self._emit(job, {"type": kind, "text": text})

    def _update_positions(self) -> None:
        for pos, j in enumerate(self._waiting, start=1):
            if j.queue_position != pos:
                j.queue_position = pos
                self._emit(j, {"type": "queued", "position": pos})

    async def _run(self, job: Job) -> None:
        settings = get_settings()
        req = job.request
        extra = {"document_id": job.document_id}
        status, error, markdown = STATUS_FAILED, None, ""
        cancelled = False
        try:
            assert self._sem is not None
            async with self._sem:
                self._waiting.remove(job)
                job.queue_position = 0
                self._update_positions()

                job.status = STATUS_PROCESSING
                job.started_at = time.perf_counter()
                await _set_status(job.document_id, STATUS_PROCESSING)
                self._emit(job, {"type": "status", "status": STATUS_PROCESSING})
                log.info("job started", extra=extra)

                chunks = split_into_chunks(req.text, settings.chunk_chars)
                parts: list[str] = []
                for idx, chunk in enumerate(chunks, start=1):
                    if len(chunks) > 1:
                        job.chunk = {"index": idx, "total": len(chunks)}
                        self._emit(job, {"type": "chunk", **job.chunk})
                        if idx > 1:
                            self._append(job, "content", "\n\n")
                    outline = "\n".join(ln for ln in "\n\n".join(parts).splitlines() if re.match(r"^#{1,4}\s", ln))
                    prompt = build_user_prompt(
                        chunk,
                        job.template_instructions,
                        req.custom_instructions,
                        req.title,
                        idx,
                        len(chunks),
                        outline,
                    )
                    buf: list[str] = []
                    async for ev in stream_chat(SYSTEM_PROMPT, prompt, req.think_level):
                        if ev.kind == "content":
                            buf.append(ev.text)
                        self._append(job, ev.kind, ev.text)
                    parts.append(clean_output("".join(buf)))

                markdown = "\n\n".join(p for p in parts if p).strip()
                if markdown:
                    status = STATUS_COMPLETED
                else:
                    error = "The model returned an empty response."
        except asyncio.CancelledError:
            cancelled = True
            if self._shutting_down:
                status, error = STATUS_FAILED, "Interrupted by a server restart. Please re-format."
            else:
                status, error = STATUS_CANCELLED, "Cancelled."
            markdown = clean_output(job.markdown)
        except LLMError as exc:
            error = str(exc)
            markdown = clean_output(job.markdown)
        except Exception:
            log.exception("job crashed", extra=extra)
            error = "Internal error while formatting. Check the server logs."
            markdown = clean_output(job.markdown)
        finally:
            if job in self._waiting:
                self._waiting.remove(job)
                self._update_positions()

        # Persist even if we were cancelled; shield so a second cancel can't interrupt the write.
        await asyncio.shield(self._finish(job, status, markdown, error))
        log.info("job %s", status, extra={**extra, "duration_ms": int((time.perf_counter() - job.started_at) * 1000)})
        if cancelled:
            raise asyncio.CancelledError

    async def _finish(self, job: Job, status: str, markdown: str, error: str | None) -> None:
        duration_ms = int((time.perf_counter() - job.started_at) * 1000) if job.status == STATUS_PROCESSING else 0
        out: dict[str, Any] | None = None
        try:
            async with SessionLocal() as db:
                doc = await db.get(Document, job.document_id)
                if doc is not None:
                    # Keep the previous good result when a re-format fails or is cancelled.
                    if status == STATUS_COMPLETED or not doc.formatted_markdown:
                        doc.formatted_markdown = markdown
                    if status == STATUS_COMPLETED and not job.request.title.strip():
                        doc.title = title_from_markdown(markdown) or doc.title
                    doc.status = status
                    doc.error = error
                    doc.duration_ms = duration_ms
                    await db.commit()
                    await db.refresh(doc)
                    await db.refresh(doc, ["template"])
                    out = document_out(doc)
        except Exception:
            log.exception("failed to persist job result", extra={"document_id": job.document_id})
            status, error = STATUS_FAILED, "Could not save the result."

        job.status = status
        job.final_event = terminal_event(status, out, error)
        self._emit(job, job.final_event)
        self._emit(job, END)
        job.subscribers.clear()

        def _forget() -> None:
            if self._jobs.get(job.document_id) is job:
                del self._jobs[job.document_id]

        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().call_later(RETAIN_FINISHED_SECONDS, _forget)


async def _set_status(document_id: int, status: str) -> None:
    async with SessionLocal() as db:
        await db.execute(update(Document).where(Document.id == document_id).values(status=status, error=None))
        await db.commit()


async def recover_interrupted_jobs() -> int:
    """Mark jobs left queued/processing by a previous process as failed."""
    async with SessionLocal() as db:
        result = await db.execute(
            update(Document)
            .where(Document.status.in_(ACTIVE_STATUSES))
            .values(status=STATUS_FAILED, error="Interrupted by a server restart. Please re-format.")
        )
        await db.commit()
        return result.rowcount or 0


job_manager = JobManager()
