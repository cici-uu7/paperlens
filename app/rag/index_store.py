"""Index persistence and retrieval helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from app.models.schemas import ChunkRecord
from app.rag.errors import IndexNotBuiltError

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover - depends on runtime environment
    faiss = None

try:
    import numpy as np
except ImportError:  # pragma: no cover - depends on runtime environment
    np = None


def _normalize_vector(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _dot(left: List[float], right: List[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


@dataclass
class RetrievalHit:
    chunk: ChunkRecord
    score: float


class IndexStore:
    def __init__(
        self,
        records: List[ChunkRecord],
        vectors: List[List[float]],
        backend: str,
        index: Optional[object] = None,
    ) -> None:
        self.records = records
        self.vectors = [_normalize_vector(vector) for vector in vectors]
        self.backend = backend
        self.index = index

    @classmethod
    def build(cls, records: List[ChunkRecord], vectors: List[List[float]]) -> "IndexStore":
        normalized_vectors = [_normalize_vector(vector) for vector in vectors]
        if records and normalized_vectors and faiss is not None and np is not None:
            matrix = np.array(normalized_vectors, dtype="float32")
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            return cls(records=records, vectors=normalized_vectors, backend="faiss", index=index)
        return cls(records=records, vectors=normalized_vectors, backend="json")

    def save(self, output_dir: Path) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = output_dir / "chunk_metadata.jsonl"
        with metadata_path.open("w", encoding="utf-8") as handle:
            for record in self.records:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

        build_info = {
            "backend": self.backend,
            "chunk_count": len(self.records),
            "vector_dim": len(self.vectors[0]) if self.vectors else 0,
        }
        (output_dir / "build_info.json").write_text(
            json.dumps(build_info, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if self.backend == "faiss" and self.index is not None and faiss is not None:
            faiss.write_index(self.index, str(output_dir / "faiss.index"))
        else:
            (output_dir / "vector_store.json").write_text(
                json.dumps(self.vectors, ensure_ascii=False),
                encoding="utf-8",
            )

        return output_dir

    @classmethod
    def load(cls, output_dir: Path) -> "IndexStore":
        output_dir = Path(output_dir)
        build_info_path = output_dir / "build_info.json"
        metadata_path = output_dir / "chunk_metadata.jsonl"
        if not build_info_path.exists():
            raise IndexNotBuiltError(f"Index metadata not found: {build_info_path}")
        if not metadata_path.exists():
            raise IndexNotBuiltError(f"Chunk metadata not found: {metadata_path}")

        build_info = json.loads(build_info_path.read_text(encoding="utf-8"))

        records: List[ChunkRecord] = []
        with metadata_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(ChunkRecord(**json.loads(line)))

        backend = build_info["backend"]
        if backend == "faiss":
            faiss_path = output_dir / "faiss.index"
            if faiss is not None and faiss_path.exists():
                index = faiss.read_index(str(faiss_path))
                vectors = []
                return cls(records=records, vectors=vectors, backend=backend, index=index)
            raise IndexNotBuiltError(
                f"FAISS index is unavailable or missing at {faiss_path}. "
                "Rebuild the index or install faiss."
            )

        vector_store_path = output_dir / "vector_store.json"
        if not vector_store_path.exists():
            raise IndexNotBuiltError(f"Vector store not found: {vector_store_path}")
        vectors = json.loads(vector_store_path.read_text(encoding="utf-8"))
        if records and vectors and len(records) != len(vectors):
            raise IndexNotBuiltError(
                "Index metadata and vector store are out of sync. Rebuild the index."
            )
        return cls(records=records, vectors=vectors, backend="json")

    def search(self, query_vector: List[float], top_k: int = 5) -> List[RetrievalHit]:
        normalized_query = _normalize_vector(query_vector)
        if self.backend == "faiss" and self.index is not None and faiss is not None and np is not None:
            query = np.array([normalized_query], dtype="float32")
            scores, indices = self.index.search(query, top_k)
            hits: List[RetrievalHit] = []
            for score, index in zip(scores[0], indices[0]):
                if index < 0:
                    continue
                hits.append(RetrievalHit(chunk=self.records[int(index)], score=float(score)))
            return hits

        scored = [
            RetrievalHit(chunk=record, score=_dot(vector, normalized_query))
            for record, vector in zip(self.records, self.vectors)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]
