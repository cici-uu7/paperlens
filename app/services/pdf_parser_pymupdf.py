"""PyMuPDF-backed PDF parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.services.parser_base import PdfParser

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - depends on runtime environment
    fitz = None


class PyMuPDFParser(PdfParser):
    name = "pymupdf"

    def parse(self, pdf_path: Path) -> Dict[str, Any]:
        if fitz is None:
            raise RuntimeError("PyMuPDF is not installed in the active environment")

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF does not exist: {pdf_path}")

        document = fitz.open(pdf_path)
        try:
            pages: List[Dict[str, Any]] = []
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                blocks: List[Dict[str, Any]] = []
                for block_index, block in enumerate(page.get_text("blocks"), start=1):
                    x0, y0, x1, y1, text, _, block_type = block[:7]
                    cleaned_text = " ".join(str(text).split())
                    if not cleaned_text:
                        continue
                    blocks.append(
                        {
                            "block_id": f"p{page_index + 1}_b{block_index}",
                            "block_type": int(block_type),
                            "text": cleaned_text,
                            "bbox": [float(x0), float(y0), float(x1), float(y1)],
                        }
                    )
                pages.append(
                    {
                        "page_num": page_index + 1,
                        "blocks": blocks,
                        "text": "\n".join(item["text"] for item in blocks),
                    }
                )

            return {
                "doc_id": pdf_path.stem,
                "doc_name": pdf_path.name,
                "title": document.metadata.get("title") or pdf_path.stem,
                "parser": self.name,
                "page_count": int(document.page_count),
                "pages": pages,
                "metadata": {
                    "source_path": str(pdf_path),
                    "format": "pdf",
                    "producer": document.metadata.get("producer", ""),
                },
            }
        finally:
            document.close()
