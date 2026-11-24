import io
import json

from docx import Document as DocxDocument


async def make_document(client, markdown="# Report\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n- item") -> int:
    import app.jobs
    from tests.test_jobs import stream_events

    original = app.jobs.stream_chat

    async def fake(system, user, think="low"):
        from app.services.llm import StreamEvent

        yield StreamEvent("content", markdown)

    app.jobs.stream_chat = fake
    try:
        resp = await client.post("/api/jobs", json={"text": "raw"})
        doc_id = resp.json()["document_id"]
        await stream_events(client, doc_id)
    finally:
        app.jobs.stream_chat = original
    return doc_id


# --------------------------------------------------------------------------- health & middleware


async def test_health_endpoints(client):
    assert (await client.get("/api/health/live")).json() == {"status": "ok"}
    ready = await client.get("/api/health/ready")
    assert ready.status_code == 200 and ready.json()["database"] is True
    full = (await client.get("/api/health")).json()
    assert full["database"] is True
    assert full["llm"]["reachable"] is False  # tests point at an unroutable LLM
    assert full["status"] == "degraded"
    assert full["jobs"] == {"running": 0, "queued": 0}


async def test_request_id_and_security_headers(client):
    resp = await client.get("/api/health/live", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    generated = (await client.get("/api/health/live", headers={"X-Request-ID": "bad id with spaces"})).headers
    assert generated["X-Request-ID"] != "bad id with spaces" and len(generated["X-Request-ID"]) == 16


async def test_unhandled_errors_return_json_500(client, monkeypatch):
    def boom(_):
        raise RuntimeError("secret internals")

    monkeypatch.setattr("app.routers.documents.document_summary", boom)
    await make_document(client)
    resp = await client.get("/api/documents")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == resp.headers["X-Request-ID"]
    assert "secret" not in resp.text


# --------------------------------------------------------------------------- templates


async def test_builtin_templates_are_seeded_and_read_only(client):
    templates = (await client.get("/api/templates")).json()
    builtin = [t for t in templates if t["is_builtin"]]
    assert len(builtin) == 13
    assert {"letterhead", "contract"} <= {t["slug"] for t in builtin}
    assert builtin[0]["slug"] == "clean-structure"
    assert (await client.put(f"/api/templates/{builtin[0]['id']}", json={"name": "x"})).status_code == 403
    assert (await client.delete(f"/api/templates/{builtin[0]['id']}")).status_code == 403


async def test_custom_template_crud(client):
    created = await client.post(
        "/api/templates", json={"name": "Weekly Status", "instructions": "Format as a weekly status update."}
    )
    assert created.status_code == 201
    tpl = created.json()
    assert tpl["slug"].startswith("weekly-status-") and not tpl["is_builtin"]

    updated = await client.put(f"/api/templates/{tpl['id']}", json={"name": "Weekly Status v2"})
    assert updated.json()["name"] == "Weekly Status v2"
    assert updated.json()["instructions"] == "Format as a weekly status update."

    assert (await client.delete(f"/api/templates/{tpl['id']}")).status_code == 204
    assert (await client.delete(f"/api/templates/{tpl['id']}")).status_code == 404
    assert (await client.post("/api/templates", json={"name": "", "instructions": "x"})).status_code == 422


# --------------------------------------------------------------------------- documents


async def test_document_update_search_and_delete(client):
    doc_id = await make_document(client)
    resp = await client.put(
        f"/api/documents/{doc_id}", json={"title": "Quarterly — Review", "formatted_markdown": "# Edited"}
    )
    assert resp.json()["title"] == "Quarterly — Review"
    assert resp.json()["formatted_markdown"] == "# Edited"

    assert len((await client.get("/api/documents", params={"q": "quarterly"})).json()) == 1
    assert (await client.get("/api/documents", params={"q": "nothing-matches"})).json() == []

    assert (await client.delete(f"/api/documents/{doc_id}")).status_code == 204
    assert (await client.get(f"/api/documents/{doc_id}")).status_code == 404


async def test_exports(client):
    doc_id = await make_document(client)

    md = await client.get(f"/api/documents/{doc_id}/export", params={"format": "md"})
    assert md.text.startswith("# Report")
    assert "filename*=UTF-8''Report.md" in md.headers["content-disposition"]

    html = await client.get(f"/api/documents/{doc_id}/export", params={"format": "html"})
    assert "<table>" in html.text and "<title>Report</title>" in html.text
    assert html.headers["content-security-policy"] == "sandbox"

    docx = await client.get(f"/api/documents/{doc_id}/export", params={"format": "docx"})
    parsed = DocxDocument(io.BytesIO(docx.content))
    assert parsed.paragraphs[0].style.name == "Heading 1"
    assert len(parsed.tables) == 1

    pdf = await client.get(f"/api/documents/{doc_id}/export", params={"format": "pdf"})
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    assert (await client.get(f"/api/documents/{doc_id}/export", params={"format": "exe"})).status_code == 422


async def test_export_of_empty_document_is_rejected(client):
    doc_id = await make_document(client, markdown="   ")
    resp = await client.get(f"/api/documents/{doc_id}/export", params={"format": "pdf"})
    assert resp.status_code == 400


# --------------------------------------------------------------------------- extraction


def _docx_bytes() -> bytes:
    d = DocxDocument()
    d.add_paragraph("Hello from Word")
    table = d.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "left"
    table.cell(0, 1).text = "right"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


async def test_extract_supported_files(client):
    txt = await client.post(
        "/api/extract", files={"file": ("meeting_notes.txt", b"line one\r\n\r\n\r\n\r\nline two  ")}
    )
    assert txt.status_code == 200
    body = txt.json()
    assert body["text"] == "line one\n\n\nline two"  # CRLF normalised, blank runs capped, trailing spaces trimmed
    assert body["title"] == "meeting notes"

    docx = await client.post("/api/extract", files={"file": ("w.docx", _docx_bytes())})
    assert "Hello from Word" in docx.json()["text"] and "left | right" in docx.json()["text"]

    html = b"<html><script>alert(1)</script><body><h1>Title</h1><p>Para</p></body></html>"
    extracted = (await client.post("/api/extract", files={"file": ("p.html", html)})).json()["text"]
    assert "Title" in extracted and "alert" not in extracted


async def test_extract_rejects_bad_input(client, settings):
    assert (await client.post("/api/extract", files={"file": ("a.exe", b"MZ")})).status_code == 415
    assert (await client.post("/api/extract", files={"file": ("a.pdf", b"not a pdf")})).status_code == 422
    assert (await client.post("/api/extract", files={"file": ("a.txt", b"   ")})).status_code == 422
    settings.max_upload_mb = 0
    resp = await client.post("/api/extract", files={"file": ("a.txt", b"too big")})
    assert resp.status_code == 413
    assert json.loads(resp.text)["detail"].startswith("File exceeds")
