"""Stand-in for ChatGoogleGenerativeAI so the whole stack can be tested without a Gemini key.

Everything else stays real: RabbitMQ, object storage, PaddleOCR, the prompts, the output parsers,
validation, Prometheus metrics and Langfuse tracing. Only the model call is replaced by a
LangChain chat model that builds a deterministic answer from the OCR'd text in the prompt and
reports token usage, so the token, cost and latency metrics and the Langfuse generation are recorded
exactly as with Gemini.
"""
import json
import os
import random
import re
import time
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

LINE = re.compile(r"^\s*\[L(\d+)\] \(p\d+\) (.*)$", re.M)
PO = re.compile(r"\b(?:PO|WO|P\.O\.)\s*(?:#|No\.?|Number)?\s*:?\s*(\d{3,})", re.I)
JOB = re.compile(r"\bJob\s*(?:#|No\.?|Number)?\s*:?\s*(\d{3,})", re.I)
DATE = re.compile(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b")
QTY = re.compile(r"(\d+(?:\.\d+)?)\s*$")


class FakeGemini(BaseChatModel):
    model: str = "fake-gemini"
    timeout: Optional[float] = None
    max_retries: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake-gemini"

    def _generate(self, messages: List[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        prompt = "\n".join(str(m.content) for m in messages)
        time.sleep(random.uniform(*map(float, os.getenv("FAKE_LLM_LATENCY", "0.3,1.2").split(","))))
        text = answer_columns(prompt) if "Columns to extract:" in prompt else answer_invoice(prompt)
        usage = {"input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4,
                 "total_tokens": len(prompt) // 4 + len(text) // 4}
        message = AIMessage(content=text, usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=message)], llm_output={"usage_metadata": usage})


def document_lines(prompt: str) -> List[tuple]:
    """[(n, text)] for the numbered lines; the invoice prompt has plain lines, numbered here."""
    numbered = [(int(n), t.strip()) for n, t in LINE.findall(prompt)]
    if numbered:
        return numbered
    body = prompt.split("OCR Text:")[-1] if "OCR Text:" in prompt else prompt
    return [(i, t.strip()) for i, t in enumerate(body.splitlines(), 1) if t.strip()]


def first(pattern, lines) -> Optional[tuple]:
    for n, text in lines:
        m = pattern.search(text)
        if m:
            return n, m.group(1)
    return None


def items(lines) -> List[tuple]:
    """Lines that end in a quantity, like "Shingles (sq) 41.66"."""
    found = []
    for n, text in lines:
        m = QTY.search(text)
        if m and len(text) > len(m.group(1)) + 3 and not DATE.search(text):
            found.append((n, text, m.group(1)))
    return found[:20]


def answer_invoice(prompt: str) -> str:
    lines = document_lines(prompt)
    po, job, date = first(PO, lines), first(JOB, lines), first(DATE, lines)
    line_items = []
    for i, (_, text, qty) in enumerate(items(lines), 1):
        line_items.append({"line_no": str(i), "product_description": text[: -len(qty)].strip(" :-|"),
                           "quantity": int(float(qty)) if float(qty).is_integer() else None})
    header = {"purchase_order_number": po and po[1], "job_number": job and job[1], "date_ordered": date and date[1]}
    return json.dumps({"extraction": [{"header": header, "line_items": line_items}]})


def answer_columns(prompt: str) -> str:
    columns_block = prompt.split("Columns to extract:")[1].split("The document text")[0]
    try:
        columns = json.loads(columns_block.strip())
    except ValueError:
        columns = [c.strip(" -*\"'") for c in re.split(r"[,\n]", columns_block) if c.strip(" -*\"'")]
    lines = document_lines(prompt)
    by_kind = {"po": first(PO, lines), "job": first(JOB, lines), "date": first(DATE, lines)}
    rows = []
    for n, text, qty in items(lines) or [(None, None, None)]:
        cells = []
        for column in columns:
            key = column.lower()
            hit = None
            if "po" in key.split() or "order number" in key:
                hit = by_kind["po"]
            elif "job" in key:
                hit = by_kind["job"]
            elif "date" in key:
                hit = by_kind["date"]
            elif ("qty" in key or "quantity" in key) and n:
                hit = (n, qty)
            elif ("description" in key or "item" in key) and n:
                hit = (n, text[: -len(qty)].strip(" :-|"))
            cells.append({"column": column, "value": hit and hit[1], "line": hit and hit[0]})
        rows.append({"cells": cells})
    return json.dumps({"rows": rows})
