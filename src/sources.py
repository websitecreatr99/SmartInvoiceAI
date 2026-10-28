"""Flatten extractions into table rows and attach where each value came from.

Every cell is {"value": ..., "source": {"page", "line", "text", "confidence"} | None},
so the UI can show the document line behind each value.
"""
import re
from typing import List, Optional

from pydantic import ValidationError

from .common import ColumnExtraction, describe_validation_error
from .document_reader import Line

# Header fields shown as columns when the user doesn't name their own.
INVOICE_COLUMNS = [
    ("PO number", "purchase_order_number"),
    ("Job name", "job_name"),
    ("Job number", "job_number"),
    ("Project number", "project_number"),
    ("Quote number", "quote_number"),
    ("Date ordered", "date_ordered"),
    ("Delivery date", "delivery_date"),
    ("Vendor", "vendor.name"),
    ("Ship to", "ship_to.name"),
    ("Bill to", "bill_to.name"),
    ("Buyer", "buyer_contact.name"),
    ("Buyer email", "buyer_contact.email"),
    ("Ship via", "ship_via"),
    ("Payment terms", "payment_terms"),
]

# Share of a value's words that must appear on one line to call it the source.
MIN_OVERLAP = 0.6


def _norm(text) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text).lower()))


def numbered_text(lines: List[Line]) -> str:
    """Document text with line ids the model can cite back."""
    return "\n".join(f"[L{i}] (p{line.page}) {line.text}" for i, line in enumerate(lines, start=1))


def _source(lines: List[Line], i: int) -> dict:
    line = lines[i - 1]
    return {"page": line.page, "line": i, "text": line.text, "confidence": line.confidence}


def _overlap(target: str, text: str) -> float:
    if f" {target} " in f" {text} ":
        return 1.0
    tokens = set(target.split())
    return len(tokens & set(text.split())) / len(tokens)


def locate(value, lines: List[Line], hint: Optional[int] = None) -> Optional[dict]:
    """Find the line a value was read from, preferring the model's cited line when it checks out."""
    target = _norm(value) if value is not None else ""
    if not target:
        return None
    normed = [_norm(line.text) for line in lines]
    valid_hint = hint is not None and 1 <= hint <= len(lines)
    if valid_hint and _overlap(target, normed[hint - 1]) >= MIN_OVERLAP:
        return _source(lines, hint)

    scores = [_overlap(target, text) for text in normed]
    best = max(range(len(scores)), key=scores.__getitem__, default=None)
    if best is not None and scores[best] >= MIN_OVERLAP:
        return _source(lines, best + 1)
    # The model may have reformatted the value (dates, amounts); trust its citation then.
    return _source(lines, hint) if valid_hint else None


def _cell(value, lines: List[Line], hint: Optional[int] = None) -> dict:
    return {"value": value, "source": locate(value, lines, hint)}


def _get(obj, path: str):
    for key in path.split("."):
        obj = obj.get(key) if isinstance(obj, dict) else None
    return obj


def invoice_fields(structured: dict, lines: List[Line]) -> dict:
    """One row per extracted order, with the invoice header fields as columns."""
    rows = [
        {label: _cell(_get(order.get("header"), path), lines) for label, path in INVOICE_COLUMNS}
        for order in structured.get("extraction") or []
    ]
    return {"columns": [label for label, _ in INVOICE_COLUMNS], "rows": rows}


def column_fields(data: dict, columns: List[str], lines: List[Line]) -> dict:
    """Rows for the user's own columns, keyed by the names they asked for."""
    try:
        parsed = ColumnExtraction(**data)
    except ValidationError as e:
        raise ValueError(f"Validation Error: {describe_validation_error(e)}")

    by_key = {c.lower(): c for c in columns}
    rows = []
    for row in parsed.rows:
        out = {c: {"value": None, "source": None} for c in columns}
        for cell in row.cells:
            column = by_key.get(cell.column.strip().lower())
            if column and cell.value is not None:
                out[column] = _cell(cell.value, lines, cell.line)
        if any(c["value"] is not None for c in out.values()):
            rows.append(out)
    return {"columns": columns, "rows": rows}
