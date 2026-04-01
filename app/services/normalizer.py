"""Normalize parser outputs into shared PaperLens schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.models.schemas import NormalizedDocument, NormalizedElement, NormalizedPage


def _looks_like_heading(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) > 120:
        return False
    if stripped.endswith((".", "?", "!", "。", "？", "！", ":", "：")):
        return False
    return stripped.isupper() or stripped == stripped.title()


def normalize_pymupdf_document(parsed_document: Dict[str, Any]) -> NormalizedDocument:
    pages: List[NormalizedPage] = []
    for page in parsed_document.get("pages", []):
        elements: List[NormalizedElement] = []
        for block in page.get("blocks", []):
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            element_type = "heading" if _looks_like_heading(text) else "paragraph"
            elements.append(
                NormalizedElement(
                    element_id=block.get("block_id", ""),
                    type=element_type,
                    text=text,
                    bbox=block.get("bbox"),
                    metadata={"block_type": block.get("block_type", 0)},
                )
            )
        pages.append(NormalizedPage(page_num=int(page.get("page_num", 0)), elements=elements))

    return NormalizedDocument(
        doc_id=str(parsed_document.get("doc_id", "")),
        doc_name=str(parsed_document.get("doc_name", "")),
        title=str(parsed_document.get("title", "")),
        parser=str(parsed_document.get("parser", "pymupdf")),
        page_count=int(parsed_document.get("page_count", len(pages))),
        pages=pages,
        metadata=dict(parsed_document.get("metadata", {})),
    )


def normalize_structured_document(parsed_document: Dict[str, Any]) -> NormalizedDocument:
    pages: List[NormalizedPage] = []
    for page in parsed_document.get("pages", []):
        page_num = int(page.get("page_num", 0))
        elements: List[NormalizedElement] = []
        for element_index, element in enumerate(page.get("elements", []), start=1):
            text = str(element.get("text", "")).strip()
            if not text:
                continue
            section_path = element.get("section_path", [])
            if not isinstance(section_path, list):
                section_path = [str(section_path)]
            metadata = element.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {"raw_metadata": metadata}
            elements.append(
                NormalizedElement(
                    element_id=element.get("element_id", f"p{page_num}_e{element_index}"),
                    type=str(element.get("type", "paragraph")),
                    text=text,
                    bbox=element.get("bbox"),
                    level=str(element.get("level", "")),
                    section_path=[str(item) for item in section_path],
                    metadata=metadata,
                )
            )
        pages.append(NormalizedPage(page_num=page_num, elements=elements))

    return NormalizedDocument(
        doc_id=str(parsed_document.get("doc_id", "")),
        doc_name=str(parsed_document.get("doc_name", "")),
        title=str(parsed_document.get("title", "")),
        parser=str(parsed_document.get("parser", "structured")),
        page_count=int(parsed_document.get("page_count", len(pages))),
        pages=pages,
        metadata=dict(parsed_document.get("metadata", {})),
    )


def normalize_parsed_document(parsed_document: Dict[str, Any]) -> NormalizedDocument:
    pages = parsed_document.get("pages", [])
    if pages and isinstance(pages[0], dict):
        if "blocks" in pages[0]:
            return normalize_pymupdf_document(parsed_document)
        if "elements" in pages[0]:
            return normalize_structured_document(parsed_document)

    parser_name = str(parsed_document.get("parser", ""))
    if parser_name == "pymupdf":
        return normalize_pymupdf_document(parsed_document)
    return normalize_structured_document(parsed_document)


def save_normalized_document(document: NormalizedDocument, output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{document.doc_id}.json"
    output_path.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def save_normalized_documents(
    documents: Iterable[NormalizedDocument],
    output_dir: Path,
) -> List[Path]:
    return [save_normalized_document(document, output_dir) for document in documents]
