"""Chunk normalized documents into retrieval-ready records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from app.models.schemas import ChunkRecord, NormalizedDocument, NormalizedElement, NormalizedPage


def load_normalized_document(path: Path) -> NormalizedDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    pages = [
        NormalizedPage(
            page_num=int(page["page_num"]),
            elements=[NormalizedElement(**element) for element in page.get("elements", [])],
        )
        for page in payload.get("pages", [])
    ]
    return NormalizedDocument(
        doc_id=payload["doc_id"],
        doc_name=payload["doc_name"],
        title=payload.get("title", ""),
        parser=payload.get("parser", ""),
        page_count=int(payload.get("page_count", len(pages))),
        pages=pages,
        metadata=payload.get("metadata", {}),
    )


def _split_text(text: str, max_chars: int, overlap: int) -> List[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind(" ", start, end)
            if split_at <= start + (max_chars // 2):
                split_at = end
            end = split_at
        segment = text[start:end].strip()
        if segment:
            chunks.append(segment)
        if end >= len(text):
            break
        start = max(end - overlap, 0)
    return chunks


def chunk_normalized_document(
    document: NormalizedDocument,
    max_chars: int = 1400,
    overlap: int = 200,
) -> List[ChunkRecord]:
    chunks: List[ChunkRecord] = []
    current_section = ""
    current_text_parts: List[str] = []
    current_page_start = 0
    current_page_end = 0
    current_element_types: List[str] = []

    def flush() -> None:
        nonlocal current_text_parts, current_page_start, current_page_end, current_element_types
        if not current_text_parts:
            return
        text = "\n\n".join(current_text_parts).strip()
        chunk_index = len(chunks) + 1
        chunks.append(
            ChunkRecord(
                chunk_id=f"{document.doc_id}_c{chunk_index:04d}",
                doc_id=document.doc_id,
                doc_name=document.doc_name,
                page_start=current_page_start,
                page_end=current_page_end,
                text=text,
                section_title=current_section,
                element_types=list(dict.fromkeys(current_element_types)),
            )
        )
        current_text_parts = []
        current_page_start = 0
        current_page_end = 0
        current_element_types = []

    for page in document.pages:
        for element in page.elements:
            text_segments = _split_text(element.text, max_chars=max_chars, overlap=overlap)
            if not text_segments:
                continue

            if element.type == "heading":
                flush()
                current_section = element.text.strip()

            for segment in text_segments:
                candidate_parts = current_text_parts + [segment]
                candidate_text = "\n\n".join(candidate_parts)
                if current_text_parts and len(candidate_text) > max_chars:
                    flush()

                if current_page_start == 0:
                    current_page_start = page.page_num
                current_page_end = page.page_num
                current_text_parts.append(segment)
                current_element_types.append(element.type)

    flush()
    return chunks


def write_chunk_records(records: Iterable[ChunkRecord], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return output_path
