import zipfile

import pytest

from src import sources
from src.document_reader import Line, read_document

LINES = [Line(1, "PO # 4500-152", 0.98), Line(1, "Ship to: ACME Roofing Inc", 0.95), Line(2, "Total 10", 0.9)]


def test_locate_matches_whole_words_only():
    assert sources.locate("4500 152", LINES)["line"] == 1
    assert sources.locate("1", LINES) is None
    assert sources.locate("Acme Roofing", LINES)["text"] == "Ship to: ACME Roofing Inc"


def test_locate_prefers_a_matching_cited_line_and_falls_back_to_it():
    lines = LINES + [Line(3, "Total 10", 0.9)]
    assert sources.locate("10", lines, hint=4)["page"] == 3
    # Reformatted value the text search can't find: keep the model's citation.
    assert sources.locate("2024-09-12", lines, hint=3)["line"] == 3
    assert sources.locate("2024-09-12", lines, hint=None) is None
    assert sources.locate(None, lines, hint=1) is None


def test_invalid_column_output_is_a_validation_error():
    with pytest.raises(ValueError, match="Validation Error"):
        sources.column_fields({"rows": [{"nope": 1}]}, ["A"], LINES)


def no_ocr(path, out_dir):
    raise AssertionError("text formats must not be OCR'd")


def test_reads_text_html_and_docx_without_ocr(tmp_path):
    txt = tmp_path / "a.csv"
    txt.write_text("part,qty\n\nA-1,5\n", encoding="utf-8")
    assert read_document(str(txt), str(tmp_path), no_ocr) == [Line(1, "part,qty", None), Line(1, "A-1,5", None)]

    page = tmp_path / "a.html"
    page.write_text("<style>x{}</style><p>Invoice &amp; PO</p><div>42</div>", encoding="utf-8")
    assert [l.text for l in read_document(str(page), str(tmp_path), no_ocr)] == ["Invoice & PO", "42"]

    doc = tmp_path / "a.docx"
    with zipfile.ZipFile(doc, "w") as z:
        z.writestr("word/document.xml", '<w:body><w:p><w:r><w:t>PO</w:t></w:r><w:r><w:t xml:space="preserve"> 77</w:t></w:r></w:p><w:p/></w:body>')
    assert read_document(str(doc), str(tmp_path), no_ocr) == [Line(1, "PO 77", None)]


def test_ocr_pages_are_numbered_and_scores_made_json_safe(tmp_path):
    img = tmp_path / "scan.JPG"
    img.write_bytes(b"x")
    pages = lambda path, out: [[("A", 0.5)], [(" ", 0.1), ("B", None)]]
    assert read_document(str(img), str(tmp_path), pages) == [Line(1, "A", 0.5), Line(2, "B", None)]
    with pytest.raises(ValueError, match="Unsupported"):
        read_document(str(tmp_path / "a.exe"), str(tmp_path), pages)
