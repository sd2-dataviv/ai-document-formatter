"""Thin async client for the Ollama chat API with streaming + chunking helpers."""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from ..config import get_settings


class LLMError(RuntimeError):
    pass


@dataclass
class StreamEvent:
    kind: str  # "thinking" | "content"
    text: str


def _context_window(prompt_chars: int) -> int:
    """Pick a power-of-two num_ctx big enough for prompt + output + reasoning.

    Power-of-two buckets keep Ollama from reloading the model on every request.
    """
    prompt_tokens = prompt_chars / 3.2
    needed = int(prompt_tokens * 2.4) + 4096  # input + ~1.3x output + reasoning headroom
    ctx = 8192
    while ctx < needed and ctx < 65536:
        ctx *= 2
    return ctx


async def stream_chat(system: str, user: str, think: str = "low") -> AsyncIterator[StreamEvent]:
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "stream": True,
        "think": think,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": 0.2,
            "num_ctx": _context_window(len(system) + len(user)),
        },
    }
    timeout = httpx.Timeout(connect=10.0, read=settings.ollama_timeout, write=30.0, pool=10.0)
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=timeout) as client:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode(errors="replace")[:500]
                    raise LLMError(f"Ollama returned HTTP {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if err := data.get("error"):
                        raise LLMError(f"Ollama error: {err}")
                    msg = data.get("message") or {}
                    if msg.get("thinking"):
                        yield StreamEvent("thinking", msg["thinking"])
                    if msg.get("content"):
                        yield StreamEvent("content", msg["content"])
                    if data.get("done"):
                        break
    except httpx.ConnectError as exc:
        raise LLMError(f"Cannot reach Ollama at {settings.ollama_url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise LLMError("Timed out waiting for the model to respond.") from exc


async def ollama_status() -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=5.0) as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            names = [m["name"] for m in resp.json().get("models", [])]
            return {
                "reachable": True,
                "url": settings.ollama_url,
                "model": settings.ollama_model,
                "model_available": settings.ollama_model in names,
            }
    except Exception as exc:
        return {
            "reachable": False,
            "url": settings.ollama_url,
            "model": settings.ollama_model,
            "model_available": False,
            "error": str(exc),
        }


def split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split on paragraph boundaries (falling back to lines / hard cuts) into <= max_chars chunks."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    pieces: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            pieces.append(para)
            continue
        # Oversized paragraph: split by lines, then hard-cut if still too long.
        buf = ""
        for line in para.splitlines():
            while len(line) > max_chars:
                pieces.append(line[:max_chars])
                line = line[max_chars:]
            if len(buf) + len(line) + 1 > max_chars and buf:
                pieces.append(buf)
                buf = ""
            buf = f"{buf}\n{line}" if buf else line
        if buf:
            pieces.append(buf)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) + 2 > max_chars:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


_FENCE_RE = re.compile(r"^\s*```(?:markdown|md)?\s*\n(.*?)\n```\s*$", re.DOTALL | re.IGNORECASE)


_LINE_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# A trailing <br> (sometimes escaped as \<br>): react-markdown shows raw HTML as literal text.
_TRAILING_BR_RE = re.compile(r"\s*\\?<br\s*/?>\s*$", re.IGNORECASE)
_DASH_RULE_RE = re.compile(r"^ {0,3}-[ \t]*-[ \t]*-[ \t-]*$")
# Hyphen / non-breaking hyphen: gpt-oss likes them, but common PDF fonts (Arial) have no glyph.
_CHAR_FIXES = str.maketrans({"‐": "-", "‑": "-"})


def clean_output(markdown: str) -> str:
    """Normalise model output: unwrap a whole-document code fence and fix Markdown slips.

    Outside code blocks: a trailing ``<br>`` becomes a real Markdown line break, and a ``---``
    rule directly under a text line gets a blank line first (otherwise Markdown turns the text
    above it into a heading).
    """
    md = markdown.strip()
    if m := _FENCE_RE.match(md):
        md = m.group(1).strip()
    md = md.translate(_CHAR_FIXES)

    out: list[str] = []
    in_code = False
    for line in md.split("\n"):
        if _LINE_FENCE_RE.match(line):
            in_code = not in_code
        elif not in_code:
            if _TRAILING_BR_RE.search(line):
                line = _TRAILING_BR_RE.sub("  ", line)
            if _DASH_RULE_RE.match(line) and out and out[-1].strip():
                out.append("")
        out.append(line)
    return "\n".join(out)
