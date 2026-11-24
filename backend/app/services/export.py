"""Render formatted Markdown to HTML, DOCX and PDF."""

import html as html_lib
import io
import re
import threading
from pathlib import Path

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.tasklists import tasklists_plugin

_md = (
    MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": True})
    .enable(["table", "strikethrough"])
    .use(tasklists_plugin)
)


_CODE_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_DELIM_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")


def _is_table_delimiter(line: str) -> bool:
    if "|" not in line:
        return False
    cells = line.strip().strip("|").split("|")
    return all(_DELIM_CELL_RE.match(c) for c in cells)


def _parse_ready(markdown: str) -> str:
    """Put a blank line before tables that directly follow a paragraph line.

    GFM (and the in-app preview) lets a table interrupt a paragraph, but markdown-it does not,
    so such tables would otherwise be exported as literal pipe text.
    """
    lines = markdown.split("\n")
    out: list[str] = []
    in_code = False
    for i, line in enumerate(lines):
        if _CODE_FENCE_RE.match(line):
            in_code = not in_code
        elif (
            not in_code
            and "|" in line
            and out
            and out[-1].strip()
            and i + 1 < len(lines)
            and _is_table_delimiter(lines[i + 1])
        ):
            out.append("")
        out.append(line)
    return "\n".join(out)


def safe_filename(title: str, ext: str) -> str:
    base = re.sub(r"[^\w\- ]+", "", title).strip().replace(" ", "_")[:80] or "document"
    return f"{base}.{ext}"


# --------------------------------------------------------------------------- HTML

HTML_CSS = """
body { font-family: 'Segoe UI', -apple-system, Helvetica, Arial, sans-serif; color: #1f2937;
       line-height: 1.6; max-width: 820px; margin: 40px auto; padding: 0 24px; font-size: 15px; }
h1, h2, h3, h4 { color: #111827; line-height: 1.25; margin: 1.6em 0 0.6em; }
h1 { font-size: 2em; border-bottom: 2px solid #e5e7eb; padding-bottom: .3em; margin-top: 0; }
h2 { font-size: 1.5em; border-bottom: 1px solid #e5e7eb; padding-bottom: .25em; }
h3 { font-size: 1.2em; }
a { color: #4f46e5; }
code { background: #f3f4f6; padding: .15em .35em; border-radius: 4px; font-size: .9em;
       font-family: Consolas, 'Courier New', monospace; }
pre { background: #f3f4f6; padding: 14px 16px; border-radius: 8px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #6366f1; margin: 1em 0; padding: .2em 1em; color: #4b5563;
             background: #f9fafb; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #d1d5db; padding: 8px 12px; text-align: left; vertical-align: top; }
th { background: #f3f4f6; font-weight: 600; }
hr { border: 0; border-top: 1px solid #e5e7eb; margin: 2em 0; }
ul.contains-task-list { list-style: none; padding-left: 1.2em; }
"""


def markdown_to_html_fragment(markdown: str) -> str:
    return _md.render(_parse_ready(markdown))


def markdown_to_html(markdown: str, title: str) -> str:
    body = markdown_to_html_fragment(markdown)
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html_lib.escape(title)}</title><style>{HTML_CSS}</style></head>"
        f"<body>\n{body}\n</body></html>"
    )


# --------------------------------------------------------------------------- PDF

_FONT_CANDIDATES = [
    # (regular, bold, italic, bold-italic)
    (
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/ariali.ttf",
        "C:/Windows/Fonts/arialbi.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    ),
]


_registered_font: str | None = None


def _register_pdf_font() -> str:
    """Register a Unicode TTF family with ReportLab (core PDF fonts are Latin-1 only).

    Registering directly (instead of CSS @font-face) avoids xhtml2pdf's temp-file copy,
    which fails on Windows.
    """
    global _registered_font
    if _registered_font:
        return _registered_font

    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from xhtml2pdf import default as pisa_default

    for regular, bold, italic, bold_italic in _FONT_CANDIDATES:
        if not Path(regular).exists():
            continue
        variants = {
            "DocFont": regular,
            "DocFont-Bold": bold if Path(bold).exists() else regular,
            "DocFont-Italic": italic if Path(italic).exists() else regular,
            "DocFont-BoldItalic": bold_italic if Path(bold_italic).exists() else regular,
        }
        for name, path in variants.items():
            pdfmetrics.registerFont(TTFont(name, path))
        addMapping("DocFont", 0, 0, "DocFont")
        addMapping("DocFont", 1, 0, "DocFont-Bold")
        addMapping("DocFont", 0, 1, "DocFont-Italic")
        addMapping("DocFont", 1, 1, "DocFont-BoldItalic")
        pisa_default.DEFAULT_FONT["docfont"] = "DocFont"
        _registered_font = "DocFont"
        return _registered_font

    _registered_font = "Helvetica"
    return _registered_font


PDF_CSS = """
@page { size: a4 portrait; margin: 2cm 2cm 2.2cm 2cm;
        @frame footer { -pdf-frame-content: footer; bottom: 0.8cm; margin-left: 2cm; margin-right: 2cm; height: 1cm; } }
body { font-family: %(font)s; font-size: 10.5pt; color: #1f2937; line-height: 1.45; }
h1 { font-size: 20pt; color: #111827; border-bottom: 1.5pt solid #e5e7eb; padding-bottom: 4pt; margin: 0 0 10pt 0; }
h2 { font-size: 15pt; color: #111827; border-bottom: 0.75pt solid #e5e7eb; padding-bottom: 2pt; margin: 16pt 0 6pt 0; }
h3 { font-size: 12.5pt; color: #111827; margin: 12pt 0 4pt 0; }
h4, h5, h6 { font-size: 11pt; color: #111827; margin: 10pt 0 4pt 0; }
p { margin: 0 0 7pt 0; }
a { color: #4f46e5; text-decoration: none; }
code { font-family: Courier; font-size: 9.5pt; background-color: #f3f4f6; }
pre { font-family: Courier; font-size: 9pt; background-color: #f3f4f6; padding: 8pt; border: 0.5pt solid #e5e7eb; }
blockquote { border-left: 3pt solid #6366f1; background-color: #f9fafb; padding: 4pt 10pt;
             margin: 6pt 0; color: #4b5563; }
table { width: 100%%; margin: 6pt 0 10pt 0; }
th { background-color: #f3f4f6; font-weight: bold; border: 0.75pt solid #d1d5db; padding: 4pt 6pt; text-align: left; }
td { border: 0.75pt solid #d1d5db; padding: 4pt 6pt; vertical-align: top; }
li { margin-bottom: 2pt; }
hr { color: #e5e7eb; }
#footer { text-align: center; font-size: 8.5pt; color: #9ca3af; }
"""


_pdf_lock = threading.Lock()


def warm_up() -> None:
    """Import the PDF stack and register fonts once at startup (slow, and not thread-safe)."""
    with _pdf_lock:
        _register_pdf_font()


def markdown_to_pdf(markdown: str, title: str) -> bytes:
    # xhtml2pdf/ReportLab keep global state; serialise renders across threadpool workers.
    with _pdf_lock:
        return _markdown_to_pdf(markdown, title)


def _markdown_to_pdf(markdown: str, title: str) -> bytes:
    from xhtml2pdf import pisa  # imported lazily: heavy import

    css = PDF_CSS % {"font": _register_pdf_font()}
    body = markdown_to_html_fragment(markdown)
    # xhtml2pdf ignores <input>; render task checkboxes as text (ballot-box glyphs are
    # missing from most body fonts).
    body = re.sub(r"<input[^>]*checked[^>]*>", "[x] ", body)
    body = re.sub(r"<input[^>]*>", "[ ] ", body)
    # xhtml2pdf collapses columns whose cells are empty; give them a non-breaking space.
    body = re.sub(r"<(td|th)([^>]*)>\s*</\1>", r"<\1\2>&nbsp;</\1>", body)
    doc = (
        f"<html><head><meta charset='utf-8'><title>{html_lib.escape(title)}</title>"
        f"<style>{css}</style></head><body>{body}"
        "<div id='footer'>Page <pdf:pagenumber> of <pdf:pagecount></div></body></html>"
    )
    out = io.BytesIO()
    result = pisa.CreatePDF(doc, dest=out, encoding="utf-8")
    if result.err:
        raise RuntimeError("PDF rendering failed")
    return out.getvalue()


# --------------------------------------------------------------------------- DOCX


def _add_hyperlink(paragraph, url: str, text: str, bold=False, italic=False):
    part = paragraph.part
    r_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "4F46E5")
    rpr.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)
    if bold:
        rpr.append(OxmlElement("w:b"))
    if italic:
        rpr.append(OxmlElement("w:i"))
    new_run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _shade(paragraph, fill: str = "F3F4F6"):
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def _bottom_border(paragraph):
    ppr = paragraph._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "D1D5DB")
    pbdr.append(bottom)
    ppr.append(pbdr)


def _add_inline(paragraph, token: Token | None, base_bold=False):
    if token is None or not token.children:
        return
    bold = base_bold
    italic = strike = False
    link: str | None = None
    for child in token.children:
        t = child.type
        if t == "strong_open":
            bold = True
        elif t == "strong_close":
            bold = base_bold
        elif t == "em_open":
            italic = True
        elif t == "em_close":
            italic = False
        elif t == "s_open":
            strike = True
        elif t == "s_close":
            strike = False
        elif t == "link_open":
            link = child.attrGet("href")
        elif t == "link_close":
            link = None
        elif t in ("softbreak",):
            paragraph.add_run(" ")
        elif t == "hardbreak":
            paragraph.add_run().add_break()
        elif t == "code_inline":
            run = paragraph.add_run(child.content)
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(0xBE, 0x18, 0x5D)
        elif t == "image":
            paragraph.add_run(f"[Image: {child.content or child.attrGet('src')}]").italic = True
        elif t == "html_inline":
            if "checkbox" in child.content:
                paragraph.add_run("☑" if "checked" in child.content else "☐")
        elif t == "text":
            if link:
                _add_hyperlink(paragraph, str(link), child.content, bold, italic)
            else:
                run = paragraph.add_run(child.content)
                run.bold = bold or None
                run.italic = italic or None
                run.font.strike = strike or None


def markdown_to_docx(markdown: str, title: str) -> bytes:
    doc = DocxDocument()
    doc.core_properties.title = title

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    for section in doc.sections:
        section.left_margin = section.right_margin = Inches(1)
        section.top_margin = section.bottom_margin = Inches(0.9)

    tokens = _md.parse(_parse_ready(markdown))
    list_stack: list[dict] = []  # {"ordered": bool, "counter": int}
    item_first_para: list[bool] = []
    quote_depth = 0
    i = 0

    while i < len(tokens):
        tok = tokens[i]
        t = tok.type

        if t == "heading_open":
            level = int(tok.tag[1])
            heading = doc.add_heading(level=min(level, 9))
            _add_inline(heading, tokens[i + 1])
            i += 3
            continue

        if t == "bullet_list_open":
            list_stack.append({"ordered": False, "counter": 0})
        elif t == "ordered_list_open":
            start = tok.attrGet("start")
            list_stack.append({"ordered": True, "counter": int(start) - 1 if start else 0})
        elif t in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
        elif t == "list_item_open":
            list_stack[-1]["counter"] += 1
            item_first_para.append(True)
        elif t == "list_item_close":
            item_first_para.pop()
        elif t == "blockquote_open":
            quote_depth += 1
        elif t == "blockquote_close":
            quote_depth -= 1

        elif t == "paragraph_open":
            inline = tokens[i + 1]
            if list_stack:
                depth = len(list_stack)
                lst = list_stack[-1]
                first = item_first_para[-1] if item_first_para else False
                if lst["ordered"]:
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Inches(0.3 * depth)
                    if first:
                        p.paragraph_format.first_line_indent = Inches(-0.25)
                        p.add_run(f"{lst['counter']}. ")
                else:
                    if first:
                        style = "List Bullet" if depth == 1 else f"List Bullet {min(depth, 3)}"
                        p = doc.add_paragraph(style=style)
                    else:
                        style = "List Continue" if depth == 1 else f"List Continue {min(depth, 3)}"
                        p = doc.add_paragraph(style=style)
                p.paragraph_format.space_after = Pt(2)
                if item_first_para:
                    item_first_para[-1] = False
            elif quote_depth:
                p = doc.add_paragraph(style="Quote")
            else:
                p = doc.add_paragraph()
            _add_inline(p, inline)
            i += 3
            continue

        elif t in ("fence", "code_block"):
            code = tok.content.rstrip("\n")
            p = doc.add_paragraph()
            _shade(p)
            p.paragraph_format.left_indent = Inches(0.15 + 0.3 * len(list_stack))
            for n, line in enumerate(code.split("\n")):
                if n:
                    p.add_run().add_break()
                run = p.add_run(line)
                run.font.name = "Consolas"
                run.font.size = Pt(9.5)

        elif t == "hr":
            _bottom_border(doc.add_paragraph())

        elif t == "table_open":
            rows: list[list[tuple[Token | None, bool]]] = []
            aligns: list[str | None] = []
            j = i + 1
            row: list[tuple[Token | None, bool]] = []
            while tokens[j].type != "table_close":
                tt = tokens[j]
                if tt.type == "tr_open":
                    row = []
                elif tt.type == "tr_close":
                    rows.append(row)
                elif tt.type in ("th_open", "td_open"):
                    is_header = tt.type == "th_open"
                    if is_header:
                        style = tt.attrGet("style") or ""
                        aligns.append(str(style).replace("text-align:", "") or None)
                    inline_tok = tokens[j + 1] if tokens[j + 1].type == "inline" else None
                    row.append((inline_tok, is_header))
                j += 1
            if rows:
                cols = max(len(r) for r in rows)
                table = doc.add_table(rows=len(rows), cols=cols)
                table.style = "Table Grid"
                for r_idx, r in enumerate(rows):
                    for c_idx, (inline_tok, is_header) in enumerate(r):
                        cell = table.cell(r_idx, c_idx)
                        para = cell.paragraphs[0]
                        _add_inline(para, inline_tok, base_bold=is_header)
                        if c_idx < len(aligns) and aligns[c_idx] in ("center", "right"):
                            para.alignment = (
                                WD_ALIGN_PARAGRAPH.CENTER if aligns[c_idx] == "center" else WD_ALIGN_PARAGRAPH.RIGHT
                            )
                        if is_header:
                            tc_pr = cell._tc.get_or_add_tcPr()
                            shd = OxmlElement("w:shd")
                            shd.set(qn("w:val"), "clear")
                            shd.set(qn("w:fill"), "F3F4F6")
                            tc_pr.append(shd)
                doc.add_paragraph()
            i = j

        i += 1

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
