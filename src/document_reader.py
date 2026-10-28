"""Turn any supported upload into text lines tagged with the page they came from.

PDFs and images go through OCR; text formats and .docx are read directly, so they
skip the slow OCR stage entirely.
"""
import html
import os
import re
import zipfile
from typing import Callable, List, NamedTuple, Optional, Tuple

OCR_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
TEXT_EXTENSIONS = {".txt", ".csv", ".tsv", ".md", ".json", ".xml", ".html", ".htm"}
DOCX_EXTENSIONS = {".docx"}
SUPPORTED_EXTENSIONS = OCR_EXTENSIONS | TEXT_EXTENSIONS | DOCX_EXTENSIONS

# path, output folder -> OCR (text, confidence) pairs for each page
OcrPages = Callable[[str, str], List[List[Tuple[str, float]]]]


class Line(NamedTuple):
    page: int
    text: str
    confidence: Optional[float]


def _text_lines(raw: str) -> List[Line]:
    return [Line(1, line.strip(), None) for line in raw.splitlines() if line.strip()]


def _read_text(path: str, ext: str) -> List[Line]:
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    if ext in {".html", ".htm"}:
        raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
        raw = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", raw)
        raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return _text_lines(raw)


def _read_docx(path: str) -> List[Line]:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    paragraphs = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    text = "\n".join("".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", p)) for p in paragraphs)
    return _text_lines(html.unescape(text))


def read_document(path: str, output_root: str, ocr_pages: OcrPages) -> List[Line]:
    ext = os.path.splitext(path)[1].lower()
    if ext in OCR_EXTENSIONS:
        pages = ocr_pages(path, output_root)
        return [
            # PaddleOCR scores are numpy floats, which json can't serialise.
            Line(page, str(text).strip(), None if conf is None else round(float(conf), 4))
            for page, page_lines in enumerate(pages, start=1)
            for text, conf in page_lines
            if str(text).strip()
        ]
    if ext in TEXT_EXTENSIONS:
        return _read_text(path, ext)
    if ext in DOCX_EXTENSIONS:
        return _read_docx(path)
    raise ValueError(f"Unsupported file type: {ext or 'no extension'}")
