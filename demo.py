"""Sample results for jobs submitted without a Gemini API key (DEMO_WITHOUT_KEY=1).

Nothing is read from the uploaded file: every result is the same fictional purchase order, marked
`"demo": true` so the UI can say it is sample data. The shape matches the worker's results exactly
(`structured_data` for the invoice schema, `fields` rows whose cells cite a source line), so the
whole UI can be tried without a key and without spending any Gemini quota.
"""
from typing import List, Optional

# The fictional document the sample values "come from"; cells cite these lines.
LINES = [
    "SAMPLE PURCHASE ORDER (demo data, not read from your file)",
    "PO Number: DEMO-1001",
    "Date Ordered: 01/15/2026",
    "Delivery Date: 01/22/2026",
    "Vendor: Sample Supplies Co.",
    "Ship To: Example Builders LLC, 100 Main St, Springfield",
    "Buyer: Alex Doe  alex.doe@example.com",
    "Ship Via: Ground    Payment Terms: Net 30",
    "1  Asphalt shingles (bundle)  40  BDL  32.50",
    "2  Roofing nails 1-1/4in  6  BOX  18.00",
    "3  Drip edge 10ft  12  PCS  7.25",
    "Total: $1,495.00",
]

ITEMS = [  # (line, description, quantity, unit, unit price)
    (9, "Asphalt shingles (bundle)", 40, "BDL", "32.50"),
    (10, "Roofing nails 1-1/4in", 6, "BOX", "18.00"),
    (11, "Drip edge 10ft", 12, "PCS", "7.25"),
]

HEADER = {
    "purchase_order_number": ("DEMO-1001", 2),
    "date_ordered": ("01/15/2026", 3),
    "delivery_date": ("01/22/2026", 4),
    "vendor": ("Sample Supplies Co.", 5),
    "ship_to": ("Example Builders LLC", 6),
    "buyer": ("Alex Doe", 7),
    "buyer_email": ("alex.doe@example.com", 7),
    "ship_via": ("Ground", 8),
    "payment_terms": ("Net 30", 8),
    "total": ("$1,495.00", 12),
}

# The worker's invoice-schema table columns (src/sources.py INVOICE_COLUMNS on the worker branch).
INVOICE_COLUMNS = [
    ("PO number", "purchase_order_number"), ("Job name", None), ("Job number", None),
    ("Project number", None), ("Quote number", None), ("Date ordered", "date_ordered"),
    ("Delivery date", "delivery_date"), ("Vendor", "vendor"), ("Ship to", "ship_to"), ("Bill to", None),
    ("Buyer", "buyer"), ("Buyer email", "buyer_email"), ("Ship via", "ship_via"),
    ("Payment terms", "payment_terms"),
]

# Custom column name keywords -> header field, checked in order.
HEADER_KEYWORDS = [
    (("email",), "buyer_email"), (("po", "purchase order", "order number"), "purchase_order_number"),
    (("deliver",), "delivery_date"), (("date",), "date_ordered"), (("vendor", "supplier", "seller"), "vendor"),
    (("ship to", "address", "customer"), "ship_to"), (("buyer", "contact"), "buyer"), (("ship via", "carrier"), "ship_via"),
    (("terms",), "payment_terms"), (("total", "amount due", "grand"), "total"),
]
ITEM_KEYWORDS = [
    (("qty", "quantity"), 2), (("price", "rate", "cost"), 4), (("uom", "unit"), 3),
    (("description", "item", "product", "material", "part"), 1), (("line",), 0),
]


def _cell(value, line: Optional[int]) -> dict:
    source = {"page": 1, "line": line, "text": LINES[line - 1], "confidence": None} if line else None
    return {"value": value, "source": source}


def _matches(column: str, words) -> bool:
    name = f" {column.lower()} "
    return any(f" {w}" in name or w in name.split() for w in words)


def _header_field(column: str) -> Optional[str]:
    return next((field for words, field in HEADER_KEYWORDS if _matches(column, words)), None)


def _item_field(column: str) -> Optional[int]:
    return next((index for words, index in ITEM_KEYWORDS if _matches(column, words)), None)


def _custom_fields(columns: List[str]) -> dict:
    """One row per sample item when any column asks for item data, else a single document row."""
    per_item = any(_item_field(c) is not None for c in columns)
    rows = []
    for item in ITEMS if per_item else [None]:
        row = {}
        for column in columns:
            index, field = _item_field(column), _header_field(column)
            if item and index is not None:
                value = str(item[0] - 8) if index == 0 else str(item[index])
                row[column] = _cell(value, item[0])
            elif field:
                row[column] = _cell(*HEADER[field])
            else:
                row[column] = _cell(f"Sample {column}", None)
        rows.append(row)
    return {"columns": list(columns), "rows": rows}


def _invoice_structured() -> dict:
    value = lambda field: HEADER[field][0]
    header = {
        "purchase_order_number": value("purchase_order_number"),
        "date_ordered": value("date_ordered"),
        "delivery_date": value("delivery_date"),
        "vendor": {"name": value("vendor")},
        "ship_to": {"name": value("ship_to"), "address1": "100 Main St", "city": "Springfield"},
        "buyer_contact": {"name": value("buyer"), "email": value("buyer_email")},
        "ship_via": value("ship_via"),
        "payment_terms": value("payment_terms"),
    }
    line_items = [
        {"line_no": str(line - 8), "product_description": desc, "quantity": qty, "uom": uom, "unit_price": price,
         "currency": "USD"}
        for line, desc, qty, uom, price in ITEMS
    ]
    return {"extraction": [{"header": header, "line_items": line_items}]}


def _invoice_fields() -> dict:
    row = {label: _cell(*HEADER[field]) if field else _cell(None, None) for label, field in INVOICE_COLUMNS}
    return {"columns": [label for label, _ in INVOICE_COLUMNS], "rows": [row]}


def result(job_id: str, filename: str, columns: Optional[List[str]] = None) -> dict:
    """A worker-shaped result message holding sample data."""
    out = {"job_id": job_id, "filename": filename, "ok": True, "demo": True}
    if columns:
        out["fields"] = _custom_fields(columns)
    else:
        out["structured_data"] = _invoice_structured()
        out["fields"] = _invoice_fields()
    return out
