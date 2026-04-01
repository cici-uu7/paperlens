"""Shared RAG error types for PaperLens."""

from __future__ import annotations


class PaperLensRagError(RuntimeError):
    """Base error for retrieval and indexing failures."""


class EmbeddingConfigurationError(PaperLensRagError):
    """Raised when embedding backend settings are incomplete or invalid."""


class EmbeddingProviderError(PaperLensRagError):
    """Raised when an embedding provider call fails."""


class IndexNotBuiltError(PaperLensRagError):
    """Raised when a retrieval index is missing or incomplete."""


class LlmConfigurationError(PaperLensRagError):
    """Raised when the answer generation backend is configured incorrectly."""


class AnswerGenerationError(PaperLensRagError):
    """Raised when grounded answer generation fails."""
