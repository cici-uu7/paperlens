"""Parser selection helpers."""

from __future__ import annotations

from app.core.config import Settings
from app.services.parser_base import PdfParser
from app.services.pdf_parser_opendataloader import OpenDataLoaderPdfParser
from app.services.pdf_parser_pymupdf import PyMuPDFParser


def get_pdf_parser(settings: Settings) -> PdfParser:
    backend = settings.parser_backend.strip().lower()
    if backend == "pymupdf":
        return PyMuPDFParser()
    if backend == "opendataloader":
        if OpenDataLoaderPdfParser.is_available():
            return OpenDataLoaderPdfParser(raw_output_dir=settings.opendataloader_raw_dir)
        return PyMuPDFParser()
    raise ValueError(
        f"Unsupported PARSER_BACKEND={settings.parser_backend!r}. "
        "Expected one of: pymupdf, opendataloader."
    )
