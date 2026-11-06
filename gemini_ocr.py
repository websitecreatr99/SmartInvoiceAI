"""OCR through Gemini instead of PaddleOCR (OCR_ENGINE=gemini).

PaddleOCR needs about 3 GB of RAM; this needs next to none, so the worker fits on small
hosts (e.g. a 512 MB free tier). Gemini reads the PDF or image itself and transcribes it
line by line, and `ocr_pages` returns the same shape as ocr_pipeline.ocr_pages: for each
page, a list of (text, confidence) pairs. Gemini gives no per-line confidence, so it is None.
"""
import io
import os
import re
from typing import List, Optional, Tuple

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from ocr_pipeline import MAX_PAGES, TRANSIENT_LLM_ERRORS
from src.errors import TransientError
from src.logger_config import setup_logger

logger = setup_logger(__name__)

GEMINI_OCR_MODEL = os.getenv("GEMINI_OCR_MODEL") or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
OCR_TIMEOUT_SECONDS = float(os.getenv("GEMINI_OCR_TIMEOUT_SECONDS", "300"))
OCR_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# Types Gemini reads directly; other images are converted to PNG first.
NATIVE_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

PROMPT = """Transcribe all of the text in this document exactly as written.
- Keep the reading order. Output one line per visual line of the document.
- For tables, output one line per row with the cells separated by " | ".
- Before the text of each page, output a line "=== PAGE <n> ===", numbering pages from 1.
- Do not summarise, translate, correct spelling, or add any commentary or markdown.
- If a page has no text, output only its page marker."""

PAGE_MARKER = re.compile(r"^=+\s*PAGE\s+(\d+)\s*=+$", re.IGNORECASE)


def _pdf_page_count(data: bytes) -> Optional[int]:
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return None  # Unreadable here doesn't mean unreadable for Gemini; let it try.


def _load(path: str) -> Tuple[bytes, str]:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as f:
        data = f.read()
    if ext in NATIVE_TYPES:
        if ext == ".pdf" and MAX_PAGES:
            pages = _pdf_page_count(data)
            if pages and pages > MAX_PAGES:
                raise ValueError(f"Document has {pages} pages; the limit is {MAX_PAGES}")
        return data, NATIVE_TYPES[ext]
    # .tif/.tiff/.bmp: Gemini doesn't accept them, so send the first frame as PNG.
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        out = io.BytesIO()
        image.convert("RGB").save(out, format="PNG")
    return out.getvalue(), "image/png"


def parse_pages(text: str) -> List[List[Tuple[str, Optional[float]]]]:
    """Split the transcription into pages of (line, None); text before any marker is page 1."""
    pages: List[List[Tuple[str, Optional[float]]]] = [[]]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        marker = PAGE_MARKER.match(line)
        if marker:
            page = int(marker.group(1))
            while len(pages) < page:
                pages.append([])
            continue
        pages[-1].append((line, None))
    while len(pages) > 1 and not pages[-1]:
        pages.pop()
    return pages


def ocr_pages(path: str, output_root: str = "output") -> List[List[Tuple[str, Optional[float]]]]:
    data, mime_type = _load(path)
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_OCR_MODEL, timeout=OCR_TIMEOUT_SECONDS, max_retries=OCR_MAX_RETRIES, temperature=0
    )
    message = HumanMessage(content=[
        {"type": "text", "text": PROMPT},
        {"type": "media", "mime_type": mime_type, "data": data},
    ])
    try:
        response = llm.invoke([message])
    except TRANSIENT_LLM_ERRORS as e:
        raise TransientError(f"Gemini unavailable: {type(e).__name__}: {e}") from e
    content = response.content
    if isinstance(content, list):  # some models return a list of parts
        content = "".join(p if isinstance(p, str) else p.get("text", "") for p in content)
    return parse_pages(content or "")
