import asyncio
import json

import httpx

from app.services.llm import LLMError


async def stream_events(client: httpx.AsyncClient, doc_id: int) -> list[dict]:
    resp = await client.get(f"/api/jobs/{doc_id}/events")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


async def wait_for_status(client: httpx.AsyncClient, doc_id: int, status: str, timeout: float = 5) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if (await client.get(f"/api/documents/{doc_id}")).json()["status"] == status:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"document {doc_id} never reached {status}")


async def submit(client: httpx.AsyncClient, **body) -> dict:
    resp = await client.post("/api/jobs", json={"text": "some messy notes", **body})
    assert resp.status_code == 202, resp.text
    return resp.json()


async def test_job_runs_to_completion(client, fake_llm):
    job = await submit(client, template_id=1)
    events = await stream_events(client, job["document_id"])

    types = [e["type"] for e in events]
    assert types[0] == "snapshot"
    assert "thinking" in types and "content" in types
    assert types[-1] == "done"
    doc = events[-1]["document"]
    assert doc["status"] == "completed"
    assert doc["title"] == "Fake Title"  # derived from the H1
    assert doc["formatted_markdown"] == "# Fake Title\n\nBody text."
    assert doc["template_name"] == "Clean & Structure"

    listing = (await client.get("/api/documents")).json()
    assert [d["id"] for d in listing] == [job["document_id"]]


async def test_explicit_title_is_kept(client, fake_llm):
    job = await submit(client, title="My Title")
    events = await stream_events(client, job["document_id"])
    assert events[-1]["document"]["title"] == "My Title"


async def test_events_replay_after_job_finished(client, fake_llm):
    job = await submit(client)
    await stream_events(client, job["document_id"])
    replay = await stream_events(client, job["document_id"])
    assert replay[0]["type"] == "snapshot"
    assert replay[0]["markdown"].startswith("# Fake Title")
    assert replay[-1]["type"] == "done"


async def test_reformat_updates_same_document(client, fake_llm):
    job = await submit(client)
    await stream_events(client, job["document_id"])
    fake_llm.content = "# Second Pass\n\nNew body."
    again = await submit(client, document_id=job["document_id"])
    assert again["document_id"] == job["document_id"]
    events = await stream_events(client, job["document_id"])
    assert events[-1]["document"]["formatted_markdown"].startswith("# Second Pass")
    assert len((await client.get("/api/documents")).json()) == 1


async def test_llm_failure_marks_document_failed(client, fake_llm):
    fake_llm.error = LLMError("Cannot reach Ollama")
    job = await submit(client)
    events = await stream_events(client, job["document_id"])
    assert events[-1]["type"] == "error"
    assert "Cannot reach Ollama" in events[-1]["message"]
    doc = (await client.get(f"/api/documents/{job['document_id']}")).json()
    assert doc["status"] == "failed"
    assert doc["error"] == "Cannot reach Ollama"


async def test_failed_reformat_keeps_previous_result(client, fake_llm):
    job = await submit(client)
    await stream_events(client, job["document_id"])
    fake_llm.error = LLMError("boom")
    await submit(client, document_id=job["document_id"])
    await stream_events(client, job["document_id"])
    doc = (await client.get(f"/api/documents/{job['document_id']}")).json()
    assert doc["status"] == "failed"
    assert doc["formatted_markdown"] == "# Fake Title\n\nBody text."


async def test_cancel_running_job(client, fake_llm):
    fake_llm.delay = 30
    job = await submit(client)
    doc_id = job["document_id"]
    await wait_for_status(client, doc_id, "processing")

    resp = await client.post(f"/api/jobs/{doc_id}/cancel")
    assert resp.status_code == 202
    events = await stream_events(client, doc_id)
    assert events[-1]["type"] == "cancelled"
    assert (await client.get(f"/api/documents/{doc_id}")).json()["status"] == "cancelled"
    assert (await client.post(f"/api/jobs/{doc_id}/cancel")).status_code == 409


async def test_jobs_queue_behind_the_running_one(client, fake_llm, settings):
    assert settings.max_concurrent_jobs == 1
    fake_llm.delay = 30
    first = await submit(client)
    await wait_for_status(client, first["document_id"], "processing")

    second = await submit(client)
    assert second["status"] == "queued"
    assert second["queue_position"] == 1
    stats = (await client.get("/api/jobs/stats")).json()
    assert stats == {"running": 1, "queued": 1}

    # Cancelling the queued job removes it from the queue without running it
    await client.post(f"/api/jobs/{second['document_id']}/cancel")
    events = await stream_events(client, second["document_id"])
    assert events[-1]["type"] == "cancelled"
    await client.post(f"/api/jobs/{first['document_id']}/cancel")
    await stream_events(client, first["document_id"])


async def test_duplicate_job_for_same_document_rejected(client, fake_llm):
    fake_llm.delay = 30
    job = await submit(client)
    resp = await client.post("/api/jobs", json={"text": "x", "document_id": job["document_id"]})
    assert resp.status_code == 409
    await client.post(f"/api/jobs/{job['document_id']}/cancel")
    await stream_events(client, job["document_id"])


async def test_queue_full_returns_429(client, fake_llm, settings):
    settings.max_queued_jobs = 1
    fake_llm.delay = 30
    job = await submit(client)
    resp = await client.post("/api/jobs", json={"text": "x"})
    assert resp.status_code == 429
    await client.post(f"/api/jobs/{job['document_id']}/cancel")
    await stream_events(client, job["document_id"])


async def test_long_text_is_chunked_with_outline(client, fake_llm):
    paragraphs = [f"Paragraph {i}. " + "word " * 80 for i in range(12)]  # ~5.5k chars, CHUNK_CHARS=2000
    job = await submit(client, text="\n\n".join(paragraphs))
    events = await stream_events(client, job["document_id"])

    chunk_events = [e for e in events if e["type"] == "chunk"]
    assert len(chunk_events) >= 3
    assert len(fake_llm.prompts) == len(chunk_events)
    assert "Outline of the parts already written" not in fake_llm.prompts[0]
    assert "Outline of the parts already written:\n# Fake Title" in fake_llm.prompts[1]
    assert events[-1]["type"] == "done"


async def test_input_validation(client, fake_llm, settings):
    assert (await client.post("/api/jobs", json={"text": ""})).status_code == 422
    assert (await client.post("/api/jobs", json={"text": "   "})).status_code == 422
    assert (await client.post("/api/jobs", json={"text": "x", "template_id": 999})).status_code == 404
    assert (await client.post("/api/jobs", json={"text": "x", "document_id": 999})).status_code == 404
    assert (await client.post("/api/jobs", json={"text": "x", "think_level": "max"})).status_code == 422
    settings.max_input_chars = 10
    assert (await client.post("/api/jobs", json={"text": "x" * 11})).status_code == 413
    assert fake_llm.prompts == []


async def test_shutdown_marks_running_jobs_interrupted(client, fake_llm):
    from app.jobs import job_manager

    fake_llm.delay = 30
    job = await submit(client)
    await wait_for_status(client, job["document_id"], "processing")
    await job_manager.shutdown()
    doc = (await client.get(f"/api/documents/{job['document_id']}")).json()
    assert doc["status"] == "failed"
    assert "server restart" in doc["error"]


async def test_events_for_missing_document_404(client):
    assert (await client.get("/api/jobs/12345/events")).status_code == 404
