import io

import pytest
from docx import Document as DocxDocument

from app.jobs import provisional_title, title_from_markdown
from app.schemas import FormatRequest
from app.services.export import markdown_to_docx, markdown_to_html, markdown_to_pdf, safe_filename
from app.services.extract import ExtractionError, extract_text
from app.services.llm import _context_window, clean_output, split_into_chunks
from app.services.prompts import build_user_prompt


def test_split_short_text_is_single_chunk():
    assert split_into_chunks("  hello  ", 100) == ["hello"]


def test_split_respects_limit_and_keeps_all_content():
    paragraphs = [f"p{i} " + "x" * 50 for i in range(40)]
    text = "\n\n".join(paragraphs)
    chunks = split_into_chunks(text, 300)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_hard_cuts_giant_lines():
    chunks = split_into_chunks("y" * 1000, 300)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks) == "y" * 1000


def test_context_window_is_power_of_two_and_bounded():
    assert _context_window(100) == 8192
    assert _context_window(30_000) == 32768
    assert _context_window(10_000_000) == 65536


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("```markdown\n# Hi\n```", "# Hi"),
        ("```md\n# Hi\n\ntext\n```\n", "# Hi\n\ntext"),
        ("# Hi\n\n```python\nx=1\n```", "# Hi\n\n```python\nx=1\n```"),
    ],
)
def test_clean_output(raw, expected):
    assert clean_output(raw) == expected


def test_prompt_continuation_includes_outline_only_after_first_part():
    first = build_user_prompt("text", "Make a report", "", "", 1, 3, "")
    second = build_user_prompt("text", "Make a report", "British English", "T", 2, 3, "# Report\n## Summary")
    assert "part 1 of 3" in first and "Outline" not in first
    assert "do NOT repeat sections" in second
    assert "# Report\n## Summary" in second
    assert "British English" in second and "## Document title\nT" in second


def test_titles():
    assert title_from_markdown("intro\n# **Big** `Title`\n## x") == "Big Title"
    assert title_from_markdown("## only h2") is None
    assert provisional_title(FormatRequest(text="\n\n  first line here\nmore")) == "first line here"
    assert provisional_title(FormatRequest(text="x", source_filename="notes.final.pdf")) == "notes.final"
    assert provisional_title(FormatRequest(text="x" * 200)).endswith("…")


def test_safe_filename():
    assert safe_filename('Q3: "Plan" / v2', "pdf") == "Q3_Plan__v2.pdf"
    assert safe_filename("???", "md") == "document.md"


def test_html_export_escapes_title_and_disables_raw_html():
    html = markdown_to_html("<script>alert(1)</script>\n\n**bold**", "<Title>")
    assert "<title>&lt;Title&gt;</title>" in html
    assert "<script>" not in html
    assert "<strong>bold</strong>" in html


def test_docx_export_structure():
    md = "# H1\n\n## H2\n\nPara with **bold** and [link](https://example.com).\n\n1. one\n2. two\n\n- a\n  - nested\n\n> quote\n\n```\ncode\n```"
    doc = DocxDocument(io.BytesIO(markdown_to_docx(md, "t")))
    styles = [(p.style.name, p.text) for p in doc.paragraphs if p.text.strip()]
    assert ("Heading 1", "H1") in styles and ("Heading 2", "H2") in styles
    assert ("Normal", "1. one") in styles
    assert ("List Bullet 2", "nested") in styles
    assert ("Quote", "quote") in styles
    assert any("link" in p.text for p in doc.paragraphs)  # hyperlink text present


def test_pdf_export_handles_tables_with_empty_cells():
    pdf = markdown_to_pdf("# T\n\n| A | B |\n|---|---|\n| 1 |  |\n\n- [x] done", "t")
    assert pdf.startswith(b"%PDF")


def test_extract_unsupported_and_empty():
    with pytest.raises(ExtractionError, match="Unsupported"):
        extract_text("x.bin", b"data")
    with pytest.raises(ExtractionError, match="no readable text"):
        extract_text("x.txt", b"\n\n  \n")


def test_extract_decodes_legacy_encodings():
    assert extract_text("x.txt", "café".encode("cp1252")) == "café"


def test_extract_decodes_utf16_with_bom():
    assert extract_text("x.txt", "héllo wörld".encode("utf-16")) == "héllo wörld"
