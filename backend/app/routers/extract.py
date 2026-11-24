from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..config import get_settings
from ..schemas import ExtractOut
from ..services.extract import SUPPORTED_EXTENSIONS, ExtractionError, extract_text

router = APIRouter(prefix="/api", tags=["extract"])

_READ_CHUNK = 1024 * 1024


@router.post("/extract", response_model=ExtractOut)
async def extract(file: UploadFile = File(...)):
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024
    filename = Path(file.filename or "upload.txt").name[:255]

    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    if file.size is not None and file.size > limit:
        raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB limit.")

    data = bytearray()
    while chunk := await file.read(_READ_CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB limit.")

    try:
        # Parsing (especially PDF) is CPU-bound; keep it off the event loop.
        text = await run_in_threadpool(extract_text, filename, bytes(data))
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc

    if len(text) > settings.max_input_chars:
        raise HTTPException(
            413, f"Extracted text is {len(text):,} characters; the limit is {settings.max_input_chars:,}."
        )
    title = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return ExtractOut(filename=filename, title=title, text=text, characters=len(text))
