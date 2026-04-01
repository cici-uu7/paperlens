"""Embedding helpers for PaperLens."""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Iterable, List

from app.core.config import Settings
from app.rag.errors import EmbeddingConfigurationError, EmbeddingProviderError

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on runtime environment
    OpenAI = None


def _normalize_vector(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


_ASCII_TOKEN_PATTERN = re.compile(r"[A-Za-z]+[A-Za-z0-9]*|\d+")
_CJK_BLOCK_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


def _tokenize_text(text: str) -> List[str]:
    tokens = [match.group(0).lower() for match in _ASCII_TOKEN_PATTERN.finditer(text)]
    for block_match in _CJK_BLOCK_PATTERN.finditer(text):
        block = block_match.group(0)
        if len(block) == 1:
            tokens.append(block)
            continue
        tokens.extend(block[index : index + 2] for index in range(len(block) - 1))
    if not tokens:
        tokens = text.lower().split()
    return tokens


def tokenize_text(text: str) -> List[str]:
    return _tokenize_text(text)


def extract_anchor_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    for match in _ASCII_TOKEN_PATTERN.finditer(text):
        token = match.group(0).lower()
        if any(character.isalpha() for character in token) and token not in tokens:
            tokens.append(token)
    return tokens


class Embedder(ABC):
    model_name: str

    @abstractmethod
    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]


class HashingEmbedder(Embedder):
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.model_name = f"hashing-{dim}"

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            vector = [0.0] * self.dim
            for token in _tokenize_text(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dim
                vector[index] += 1.0
            vectors.append(_normalize_vector(vector))
        return vectors


class OpenAIEmbedder(Embedder):
    def __init__(self, settings: Settings) -> None:
        if OpenAI is None:
            raise EmbeddingConfigurationError("openai is not installed in the active environment")
        if not settings.openai_api_key:
            raise EmbeddingConfigurationError("OPENAI_API_KEY is required for OpenAI embeddings")
        if not settings.embedding_model:
            raise EmbeddingConfigurationError("EMBEDDING_MODEL is required for OpenAI embeddings")

        client_kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        self.client = OpenAI(**client_kwargs)
        self.model_name = settings.embedding_model

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        payload = [text for text in texts]
        try:
            response = self.client.embeddings.create(model=self.model_name, input=payload)
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise EmbeddingProviderError(f"Embedding request failed: {exc}") from exc
        return [list(item.embedding) for item in response.data]


def build_embedder(settings: Settings) -> Embedder:
    backend = settings.embedding_backend.strip().lower()
    if backend == "auto":
        if settings.openai_api_key and settings.embedding_model:
            return OpenAIEmbedder(settings)
        return HashingEmbedder()
    if backend == "openai":
        return OpenAIEmbedder(settings)
    if backend == "hashing":
        return HashingEmbedder()
    raise EmbeddingConfigurationError(
        f"Unsupported EMBEDDING_BACKEND '{settings.embedding_backend}'. "
        "Use one of: auto, openai, hashing."
    )
