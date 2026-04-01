from app.core.config import get_settings
from app.services.normalizer import normalize_parsed_document
from app.services.parser_factory import get_pdf_parser
from app.services.pdf_parser_opendataloader import OpenDataLoaderPdfParser
from app.services.pdf_parser_pymupdf import PyMuPDFParser


def test_parser_factory_falls_back_when_opendataloader_is_unavailable(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("PARSER_BACKEND=opendataloader\n", encoding="utf-8")
    settings = get_settings(project_root=tmp_path, env_path=env_path)

    monkeypatch.setattr(OpenDataLoaderPdfParser, "is_available", classmethod(lambda cls: False))
    parser = get_pdf_parser(settings)

    assert isinstance(parser, PyMuPDFParser)


def test_parser_factory_uses_opendataloader_when_available(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("PARSER_BACKEND=opendataloader\n", encoding="utf-8")
    settings = get_settings(project_root=tmp_path, env_path=env_path)

    monkeypatch.setattr(OpenDataLoaderPdfParser, "is_available", classmethod(lambda cls: True))
    parser = get_pdf_parser(settings)

    assert isinstance(parser, OpenDataLoaderPdfParser)
    assert parser.raw_output_dir == settings.opendataloader_raw_dir


def test_normalize_parsed_document_supports_structured_pages():
    parsed_document = {
        "doc_id": "demo",
        "doc_name": "demo.pdf",
        "title": "Demo",
        "parser": "opendataloader",
        "page_count": 1,
        "pages": [
            {
                "page_num": 1,
                "elements": [
                    {
                        "element_id": "p1_e1",
                        "type": "heading",
                        "text": "Introduction",
                        "bbox": [0.0, 0.0, 42.0, 12.0],
                        "level": "h1",
                        "section_path": ["Introduction"],
                        "metadata": {"raw_type": "header"},
                    },
                    {
                        "element_id": "p1_e2",
                        "type": "paragraph",
                        "text": "PaperLens needs a structured parser adapter.",
                        "bbox": [0.0, 16.0, 200.0, 48.0],
                    },
                ],
            }
        ],
        "metadata": {"source_path": "data/raw_docs/demo.pdf"},
    }

    normalized = normalize_parsed_document(parsed_document)

    assert normalized.parser == "opendataloader"
    assert normalized.pages[0].elements[0].level == "h1"
    assert normalized.pages[0].elements[0].section_path == ["Introduction"]
    assert normalized.pages[0].elements[1].text.startswith("PaperLens")
