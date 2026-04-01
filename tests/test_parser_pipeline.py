import json

import pytest

fitz = pytest.importorskip("fitz")

from app.services.normalizer import normalize_pymupdf_document, save_normalized_document
from app.services.pdf_parser_pymupdf import PyMuPDFParser


def test_pymupdf_parser_and_normalizer_roundtrip(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Sample Heading", fontsize=18)
    page.insert_text((72, 108), "PaperLens parser test paragraph.", fontsize=12)
    document.save(pdf_path)
    document.close()

    parser = PyMuPDFParser()
    parsed = parser.parse(pdf_path)
    normalized = normalize_pymupdf_document(parsed)

    assert normalized.doc_name == "sample.pdf"
    assert normalized.page_count == 1
    assert normalized.pages[0].page_num == 1
    assert normalized.pages[0].elements
    assert normalized.pages[0].elements[0].text

    output_dir = tmp_path / "normalized"
    output_path = save_normalized_document(normalized, output_dir)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.exists()
    assert payload["doc_name"] == "sample.pdf"
    assert payload["pages"][0]["elements"][0]["text"]
