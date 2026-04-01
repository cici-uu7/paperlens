"""Optional OpenDataLoader-backed PDF parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.services.parser_base import PdfParser

try:
    import opendataloader_pdf  # type: ignore
except ImportError:  # pragma: no cover - depends on runtime environment
    opendataloader_pdf = None


def _normalize_text(text: str) -> str:
    return " ".join(str(text).split())


def _extract_text(node: Any) -> str:
    if isinstance(node, str):
        return _normalize_text(node)
    if isinstance(node, list):
        parts = [_extract_text(item) for item in node]
        return _normalize_text(" ".join(part for part in parts if part))
    if not isinstance(node, dict):
        return ""

    for key in ("text", "content", "markdown", "html", "value"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_text(value)

    nested_keys = ("spans", "children", "items", "blocks", "elements", "tokens")
    for key in nested_keys:
        value = node.get(key)
        if isinstance(value, list):
            text = _extract_text(value)
            if text:
                return text
    return ""


def _extract_bbox(node: Dict[str, Any]) -> Optional[List[float]]:
    for key in ("bbox", "bounding_box", "box"):
        value = node.get(key)
        if isinstance(value, list) and len(value) >= 4:
            return [float(item) for item in value[:4]]
        if isinstance(value, dict):
            if {"x0", "y0", "x1", "y1"} <= set(value):
                return [float(value["x0"]), float(value["y0"]), float(value["x1"]), float(value["y1"])]
            if {"left", "top", "right", "bottom"} <= set(value):
                return [
                    float(value["left"]),
                    float(value["top"]),
                    float(value["right"]),
                    float(value["bottom"]),
                ]
    return None


def _normalize_type(value: Any) -> str:
    raw = str(value or "paragraph").strip().lower()
    if raw in {"heading", "header", "title"}:
        return "heading"
    if raw in {"table", "list", "paragraph"}:
        return raw
    if "heading" in raw or raw.startswith("h"):
        return "heading"
    return "paragraph"


def _coerce_page_num(page: Dict[str, Any], fallback: int) -> int:
    for key in ("page_num", "page", "page_number", "pageIndex"):
        value = page.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    metadata = page.get("metadata")
    if isinstance(metadata, dict):
        for key in ("page_num", "page", "page_number"):
            value = metadata.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return fallback


def _extract_elements(page: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("elements", "blocks", "items", "content"):
        value = page.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _find_pages(raw_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(raw_payload.get("pages"), list):
        return [item for item in raw_payload["pages"] if isinstance(item, dict)]
    for key in ("document", "result", "data"):
        nested = raw_payload.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("pages"), list):
            return [item for item in nested["pages"] if isinstance(item, dict)]
    return []


class OpenDataLoaderPdfParser(PdfParser):
    name = "opendataloader"

    def __init__(self, raw_output_dir: Path) -> None:
        self.raw_output_dir = Path(raw_output_dir)

    @classmethod
    def is_available(cls) -> bool:
        return opendataloader_pdf is not None

    def parse(self, pdf_path: Path) -> Dict[str, Any]:
        if opendataloader_pdf is None:
            raise RuntimeError("opendataloader-pdf is not installed in the active environment")

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF does not exist: {pdf_path}")

        self.raw_output_dir.mkdir(parents=True, exist_ok=True)
        opendataloader_pdf.convert(
            input_path=[str(pdf_path)],
            output_dir=str(self.raw_output_dir),
            format="json,markdown-with-html",
            quiet=True,
            keep_line_breaks=False,
            use_struct_tree=False,
        )

        raw_json_path = self._find_output_json(pdf_path)
        raw_payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
        pages = _find_pages(raw_payload)
        structured_pages: List[Dict[str, Any]] = []

        for fallback_page_num, page in enumerate(pages, start=1):
            page_num = _coerce_page_num(page, fallback_page_num)
            structured_elements: List[Dict[str, Any]] = []
            for element_index, element in enumerate(_extract_elements(page), start=1):
                text = _extract_text(element)
                if not text:
                    continue
                section = element.get("section_path", [])
                if not isinstance(section, list):
                    section = [section] if section else []
                structured_elements.append(
                    {
                        "element_id": element.get("element_id", f"p{page_num}_e{element_index}"),
                        "type": _normalize_type(element.get("type") or element.get("label") or element.get("kind")),
                        "text": text,
                        "bbox": _extract_bbox(element),
                        "level": str(element.get("level", "")),
                        "section_path": [str(item) for item in section],
                        "metadata": {
                            "raw_type": str(
                                element.get("type") or element.get("label") or element.get("kind") or ""
                            ),
                        },
                    }
                )
            structured_pages.append({"page_num": page_num, "elements": structured_elements})

        return {
            "doc_id": pdf_path.stem,
            "doc_name": pdf_path.name,
            "title": raw_payload.get("title") or pdf_path.stem,
            "parser": self.name,
            "page_count": len(structured_pages),
            "pages": structured_pages,
            "metadata": {
                "source_path": str(pdf_path),
                "raw_json_path": str(raw_json_path),
            },
        }

    def _find_output_json(self, pdf_path: Path) -> Path:
        candidates = sorted(self.raw_output_dir.rglob(f"{pdf_path.stem}*.json"))
        if not candidates:
            raise FileNotFoundError(
                f"OpenDataLoader did not generate a JSON output for {pdf_path.name} in {self.raw_output_dir}"
            )
        for candidate in candidates:
            if candidate.stem == pdf_path.stem:
                return candidate
        return candidates[0]
