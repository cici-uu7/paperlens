"""Serializable schema objects used across the PaperLens pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SchemaModel:
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedElement(SchemaModel):
    element_id: str
    type: str
    text: str
    bbox: Optional[List[float]] = None
    level: str = ""
    section_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedPage(SchemaModel):
    page_num: int
    elements: List[NormalizedElement] = field(default_factory=list)


@dataclass
class NormalizedDocument(SchemaModel):
    doc_id: str
    doc_name: str
    title: str
    parser: str
    page_count: int
    pages: List[NormalizedPage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkRecord(SchemaModel):
    chunk_id: str
    doc_id: str
    doc_name: str
    page_start: int
    page_end: int
    text: str
    section_title: str = ""
    element_types: List[str] = field(default_factory=list)
    char_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.char_count == 0:
            self.char_count = len(self.text)


@dataclass
class Citation(SchemaModel):
    doc_name: str
    page_num: int
    chunk_id: str
    quote: str = ""
    score: Optional[float] = None
    source_title: str = ""
    quote_original: str = ""
    quote_translation: str = ""
    quote_language: str = ""

    def __post_init__(self) -> None:
        if not self.quote_original and self.quote:
            self.quote_original = self.quote
        if not self.quote and self.quote_original:
            self.quote = self.quote_original


@dataclass
class RetrievalMetadata(SchemaModel):
    top_k: int
    hit_count: int
    latency_ms: float = 0.0


@dataclass
class AskResponse(SchemaModel):
    question: str
    answer: str
    answerable: bool
    citations: List[Citation] = field(default_factory=list)
    retrieval: Optional[RetrievalMetadata] = None
    failure_reason: Optional[str] = None


@dataclass
class EvalResult(SchemaModel):
    question_id: str
    question: str
    answerable: bool
    predicted_answer: str
    status: str
    citations: List[Citation] = field(default_factory=list)
    latency_ms: float = 0.0
    expected_doc: str = ""
    expected_page_hint: str = ""
    notes: str = ""
