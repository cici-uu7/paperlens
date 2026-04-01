"""Chunk normalized documents into retrieval-ready records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from app.models.schemas import ChunkRecord, NormalizedDocument, NormalizedElement, NormalizedPage


_SOFT_SPLIT_DELIMITERS = ["\n\n", "\n", ". ", "? ", "! ", "。", "；", "; ", ", ", " "]
_TABLE_LINE_SPLIT_RE = re.compile(r"\r?\n+")
_DEFAULT_MIN_CHUNK_CHARS = 120


@dataclass
class _ChunkDraft:
    section_title: str = ""
    text_parts: List[str] = field(default_factory=list)
    page_start: int = 0
    page_end: int = 0
    element_types: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)
    source_element_count: int = 0

    @property
    def text(self) -> str:
        return "\n\n".join(self.text_parts).strip()

    @property
    def char_count(self) -> int:
        return len(self.text)


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


def load_chunk_records(path: Path) -> List[ChunkRecord]:
    records: List[ChunkRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(ChunkRecord(**json.loads(line)))
    return records


def _normalize_segment_text(text: str) -> str:
    return " ".join(text.strip().split())


def _find_split_index(text: str, start: int, search_end: int, minimum_end: int) -> int:
    window = text[start:search_end]
    for delimiter in _SOFT_SPLIT_DELIMITERS:
        candidate = window.rfind(delimiter)
        if candidate == -1:
            continue
        split_index = start + candidate + len(delimiter)
        if split_index > minimum_end:
            return split_index
    return search_end


def _split_text(text: str, max_chars: int, overlap: int) -> List[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    chunks: List[str] = []
    start = 0
    while start < len(text):
        search_end = min(start + max_chars, len(text))
        end = search_end
        if search_end < len(text):
            minimum_end = start + max(max_chars // 2, 1)
            end = _find_split_index(text, start, search_end, minimum_end)
        segment = text[start:end].strip()
        if segment:
            chunks.append(segment)
        if search_end >= len(text):
            break
        next_start = max(end - overlap, start + 1)
        while next_start < len(text) and text[next_start].isspace():
            next_start += 1
        start = next_start
    return chunks


def _split_table_text(text: str, max_chars: int) -> List[str]:
    stripped = text.strip()
    if not stripped:
        return []

    raw_lines = [line.strip() for line in _TABLE_LINE_SPLIT_RE.split(stripped) if line.strip()]
    if len(raw_lines) <= 1:
        return _split_text(stripped, max_chars=max_chars, overlap=0)

    chunks: List[str] = []
    current_lines: List[str] = []
    for line in raw_lines:
        candidate_lines = current_lines + [line]
        candidate_text = "\n".join(candidate_lines)
        if current_lines and len(candidate_text) > max_chars:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
        else:
            current_lines = candidate_lines

    if current_lines:
        chunks.append("\n".join(current_lines))

    final_chunks: List[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            final_chunks.extend(_split_text(chunk, max_chars=max_chars, overlap=0))
    return final_chunks


def _looks_like_real_heading(text: str) -> bool:
    stripped = _normalize_segment_text(text)
    if not stripped:
        return False

    alpha_count = sum(character.isalpha() for character in stripped)
    cjk_count = sum("\u4e00" <= character <= "\u9fff" for character in stripped)
    digit_count = sum(character.isdigit() for character in stripped)
    punctuation_count = sum(not character.isalnum() and not character.isspace() for character in stripped)
    signal_count = alpha_count + cjk_count

    if signal_count == 0 and digit_count > 0:
        return False
    if signal_count < 2 and punctuation_count > 0:
        return False
    if len(stripped) <= 2:
        return False
    return True


def _make_draft(
    *,
    section_title: str,
    text_parts: List[str],
    page_start: int,
    page_end: int,
    element_types: List[str],
    metadata: Dict[str, object] | None = None,
    source_element_count: int = 0,
) -> _ChunkDraft:
    draft = _ChunkDraft(
        section_title=section_title,
        text_parts=[part for part in text_parts if part.strip()],
        page_start=page_start,
        page_end=page_end,
        element_types=list(dict.fromkeys(element_types)),
        metadata=dict(metadata or {}),
        source_element_count=source_element_count,
    )
    draft.metadata["spans_multiple_pages"] = page_start != page_end
    draft.metadata["source_element_count"] = source_element_count
    return draft


def _can_merge_drafts(left: _ChunkDraft, right: _ChunkDraft, max_chars: int) -> bool:
    if not left.text or not right.text:
        return True
    if left.metadata.get("chunk_kind") == "table" or right.metadata.get("chunk_kind") == "table":
        return False
    combined = len(left.text) + len(right.text) + 2
    return combined <= max_chars


def _merge_drafts(left: _ChunkDraft, right: _ChunkDraft) -> _ChunkDraft:
    return _make_draft(
        section_title=right.section_title or left.section_title,
        text_parts=left.text_parts + right.text_parts,
        page_start=min(left.page_start, right.page_start),
        page_end=max(left.page_end, right.page_end),
        element_types=left.element_types + right.element_types,
        metadata={
            "chunk_kind": left.metadata.get("chunk_kind") or right.metadata.get("chunk_kind") or "text",
        },
        source_element_count=int(left.metadata.get("source_element_count", 0))
        + int(right.metadata.get("source_element_count", 0)),
    )


def _merge_small_drafts(drafts: List[_ChunkDraft], max_chars: int) -> List[_ChunkDraft]:
    if not drafts:
        return []

    merged: List[_ChunkDraft] = []
    for draft in drafts:
        if (
            merged
            and draft.char_count < _DEFAULT_MIN_CHUNK_CHARS
            and _can_merge_drafts(merged[-1], draft, max_chars=max_chars)
        ):
            merged[-1] = _merge_drafts(merged[-1], draft)
            continue
        merged.append(draft)

    index = 0
    while index < len(merged) - 1:
        current = merged[index]
        next_draft = merged[index + 1]
        if current.char_count < _DEFAULT_MIN_CHUNK_CHARS and _can_merge_drafts(current, next_draft, max_chars=max_chars):
            merged[index + 1] = _merge_drafts(current, next_draft)
            del merged[index]
            continue
        index += 1
    return merged


def _buffer_is_heading_only(text_parts: List[str], element_types: List[str]) -> bool:
    return bool(text_parts) and len(text_parts) == 1 and set(element_types) == {"heading"}


def chunk_normalized_document(
    document: NormalizedDocument,
    max_chars: int = 1400,
    overlap: int = 200,
) -> List[ChunkRecord]:
    drafts: List[_ChunkDraft] = []
    current_section = ""
    current_text_parts: List[str] = []
    current_page_start = 0
    current_page_end = 0
    current_element_types: List[str] = []
    current_source_element_count = 0

    def flush() -> None:
        nonlocal current_text_parts, current_page_start, current_page_end, current_element_types, current_source_element_count
        if not current_text_parts:
            return
        drafts.append(
            _make_draft(
                section_title=current_section,
                text_parts=current_text_parts,
                page_start=current_page_start,
                page_end=current_page_end,
                element_types=current_element_types,
                metadata={"chunk_kind": "text"},
                source_element_count=current_source_element_count,
            )
        )
        current_text_parts = []
        current_page_start = 0
        current_page_end = 0
        current_element_types = []
        current_source_element_count = 0

    for page in document.pages:
        for element in page.elements:
            element_type = (element.type or "paragraph").strip().lower()
            if element_type == "table":
                text_segments = _split_table_text(element.text, max_chars=max_chars)
            else:
                text_segments = _split_text(element.text, max_chars=max_chars, overlap=overlap)
            if not text_segments:
                continue

            is_real_heading = element_type == "heading" and _looks_like_real_heading(element.text)
            if is_real_heading:
                flush()
                current_section = _normalize_segment_text(element.text)

            if element_type == "table":
                if _buffer_is_heading_only(current_text_parts, current_element_types):
                    current_text_parts = []
                    current_page_start = 0
                    current_page_end = 0
                    current_element_types = []
                    current_source_element_count = 0
                else:
                    flush()
                for segment in text_segments:
                    drafts.append(
                        _make_draft(
                            section_title=current_section,
                            text_parts=[segment],
                            page_start=page.page_num,
                            page_end=page.page_num,
                            element_types=["table"],
                            metadata={"chunk_kind": "table"},
                            source_element_count=1,
                        )
                    )
                continue

            for segment_index, segment in enumerate(text_segments):
                candidate_parts = current_text_parts + [segment]
                candidate_text = "\n\n".join(candidate_parts)
                if current_text_parts and len(candidate_text) > max_chars:
                    flush()

                if current_page_start == 0:
                    current_page_start = page.page_num
                current_page_end = page.page_num
                current_text_parts.append(segment)
                current_element_types.append(element_type)
                if segment_index == 0:
                    current_source_element_count += 1

    flush()
    merged_drafts = _merge_small_drafts(drafts, max_chars=max_chars)

    chunks: List[ChunkRecord] = []
    for index, draft in enumerate(merged_drafts, start=1):
        chunks.append(
            ChunkRecord(
                chunk_id=f"{document.doc_id}_c{index:04d}",
                doc_id=document.doc_id,
                doc_name=document.doc_name,
                page_start=draft.page_start,
                page_end=draft.page_end,
                text=draft.text,
                section_title=draft.section_title,
                element_types=list(dict.fromkeys(draft.element_types)),
                metadata=draft.metadata,
            )
        )
    return chunks


def write_chunk_records(records: Iterable[ChunkRecord], output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return output_path
