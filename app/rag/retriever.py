"""Query embedding and top-k retrieval helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import List, Optional

from app.core.config import Settings
from app.models.schemas import Citation, RetrievalMetadata
from app.rag.embedder import Embedder, build_embedder, extract_anchor_tokens
from app.rag.index_store import IndexStore, RetrievalHit


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    doc_name: str
    page_start: int
    page_end: int
    text: str
    score: float
    section_title: str = ""
    element_types: List[str] = field(default_factory=list)

    @classmethod
    def from_hit(cls, hit: RetrievalHit, score: Optional[float] = None) -> "RetrievedChunk":
        return cls(
            chunk_id=hit.chunk.chunk_id,
            doc_id=hit.chunk.doc_id,
            doc_name=hit.chunk.doc_name,
            page_start=hit.chunk.page_start,
            page_end=hit.chunk.page_end,
            text=hit.chunk.text,
            score=hit.score if score is None else score,
            section_title=hit.chunk.section_title,
            element_types=list(hit.chunk.element_types),
        )

    def to_citation(self, quote_chars: int = 220) -> Citation:
        return Citation(
            doc_name=self.doc_name,
            page_num=self.page_start,
            chunk_id=self.chunk_id,
            quote=self.text[:quote_chars].strip(),
            score=self.score,
        )


class Retriever:
    def __init__(
        self,
        index_store: IndexStore,
        embedder: Embedder,
        default_top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> None:
        self.index_store = index_store
        self.embedder = embedder
        self.default_top_k = default_top_k
        self.score_threshold = score_threshold

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        index_dir: Optional[Path] = None,
        embedder: Optional[Embedder] = None,
    ) -> "Retriever":
        store = IndexStore.load(index_dir or settings.index_dir)
        return cls(
            index_store=store,
            embedder=embedder or build_embedder(settings),
            default_top_k=settings.top_k,
            score_threshold=settings.retrieval_score_threshold,
        )

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> tuple[List[RetrievedChunk], RetrievalMetadata]:
        effective_top_k = top_k or self.default_top_k
        effective_threshold = self.score_threshold if score_threshold is None else score_threshold

        started_at = perf_counter()
        query_vector = self.embedder.embed_query(query)
        candidate_k = min(max(effective_top_k * 5, 20), len(self.index_store.records))
        raw_hits = self.index_store.search(query_vector, top_k=candidate_k)
        query_anchors = extract_anchor_tokens(query)
        rescored_hits = sorted(
            (
                RetrievedChunk.from_hit(
                    hit,
                    score=hit.score + self._metadata_bonus(hit, query_anchors),
                )
                for hit in raw_hits
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        filtered_hits = [
            hit
            for hit in rescored_hits
            if hit.score >= effective_threshold
        ][:effective_top_k]
        latency_ms = (perf_counter() - started_at) * 1000
        metadata = RetrievalMetadata(
            top_k=effective_top_k,
            hit_count=len(filtered_hits),
            latency_ms=round(latency_ms, 3),
        )
        return filtered_hits, metadata

    def retrieve_citations(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> tuple[List[Citation], RetrievalMetadata]:
        chunks, metadata = self.retrieve(
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        return [chunk.to_citation() for chunk in chunks], metadata

    @staticmethod
    def _metadata_bonus(hit: RetrievalHit, query_anchors: List[str]) -> float:
        if not query_anchors:
            return 0.0

        metadata_text = " ".join(
            part
            for part in [
                Path(hit.chunk.doc_name).stem.replace("_", " ").replace("-", " "),
                hit.chunk.section_title,
            ]
            if part
        )
        metadata_tokens = set(extract_anchor_tokens(metadata_text))
        shared = metadata_tokens.intersection(query_anchors)
        return 0.15 * len(shared)
