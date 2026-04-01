"""RAG pipeline modules for PaperLens."""

from .answer_service import AnswerService, build_grounded_messages
from .chunker import (
    chunk_normalized_document,
    load_chunk_records,
    load_normalized_document,
    write_chunk_records,
)
from .embedder import Embedder, HashingEmbedder, OpenAIEmbedder, build_embedder
from .errors import (
    AnswerGenerationError,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    IndexNotBuiltError,
    LlmConfigurationError,
    PaperLensRagError,
)
from .index_store import IndexStore, RetrievalHit
from .retriever import RetrievedChunk, Retriever

__all__ = [
    "AnswerGenerationError",
    "AnswerService",
    "EmbeddingConfigurationError",
    "EmbeddingProviderError",
    "Embedder",
    "HashingEmbedder",
    "IndexStore",
    "IndexNotBuiltError",
    "LlmConfigurationError",
    "OpenAIEmbedder",
    "PaperLensRagError",
    "RetrievedChunk",
    "RetrievalHit",
    "Retriever",
    "build_embedder",
    "build_grounded_messages",
    "chunk_normalized_document",
    "load_chunk_records",
    "load_normalized_document",
    "write_chunk_records",
]
