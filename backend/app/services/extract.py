"""Extract plain text from uploaded files."""

import io
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from pypdf import PdfReader

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".log", ".json", ".xml", ".yaml", ".yml", ".rst"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".docx", ".pdf", ".html", ".htm"}


class ExtractionError(ValueError):
    pass


def _decode(data: bytes) -> str:
    # UTF-16 only with a BOM: without one, "decoding" arbitrary bytes as UTF-16 succeeds and yields garbage.
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")  # never fails


def _from_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    parts: list[str] = []
    # Walk body in order so tables stay where they were.
    for block in doc.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = "".join(node.text or "" for node in block.iter() if node.tag.endswith("}t"))
            parts.append(text)
        elif tag == "tbl":
            for row in block.iter():
                if not row.tag.endswith("}tr"):
                    continue
                cells = []
                for cell in row.iterchildren():
                    if cell.tag.endswith("}tc"):
                        cells.append(
                            " ".join(
                                "".join(n.text or "" for n in p.iter() if n.tag.endswith("}t"))
                                for p in cell.iter()
                                if p.tag.endswith("}p")
                            ).strip()
                        )
                parts.append(" | ".join(cells))
            parts.append("")
    return "\n".join(parts)


def _from_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ExtractionError("PDF is password-protected.") from exc
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n\n".join(p for p in pages if p)
    if not text.strip():
        raise ExtractionError("No selectable text found in PDF (it may be a scanned image).")
    return text


def _from_html(data: bytes) -> str:
    soup = BeautifulSoup(_decode(data), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n")


def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(
            f"Unsupported file type '{ext or 'unknown'}'. Supported: " + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    try:
        if ext == ".docx":
            text = _from_docx(data)
        elif ext == ".pdf":
            text = _from_pdf(data)
        elif ext in {".html", ".htm"}:
            text = _from_html(data)
        else:
            text = _decode(data)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Could not read {ext} file: {exc}") from exc

    # Normalise whitespace: trim trailing spaces, collapse 3+ blank lines.
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned: list[str] = []
    blank = 0
    for ln in lines:
        blank = blank + 1 if not ln else 0
        if blank <= 2:
            cleaned.append(ln)
    result = "\n".join(cleaned).strip()
    if not result:
        raise ExtractionError("The file contains no readable text.")
    return result
