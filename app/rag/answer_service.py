"""Grounded answer generation for PaperLens."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import Settings
from app.models.schemas import AskResponse, Citation, RetrievalMetadata
from app.rag.embedder import extract_anchor_tokens, tokenize_text
from app.rag.errors import AnswerGenerationError, LlmConfigurationError
from app.rag.retriever import RetrievedChunk, Retriever

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on runtime environment
    OpenAI = None


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class AnswerDraft:
    answer: str
    answerable: bool
    cited_chunk_ids: List[str] = field(default_factory=list)
    failure_reason: Optional[str] = None


@dataclass
class _SupportSentence:
    text: str
    chunk: RetrievedChunk
    support_score: float
    overlap: int
    anchor_overlap: int


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in text)


def _default_refusal_answer(question: str) -> str:
    if _contains_cjk(question):
        return "当前检索到的文档内容不足以可靠回答这个问题。"
    return "The retrieved context is not sufficient to answer this question reliably."


def _clean_sentence(text: str) -> str:
    return " ".join(text.strip().split())


def _is_informative_sentence(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 24:
        return False

    alnum_count = sum(character.isalnum() for character in stripped)
    plus_ratio = stripped.count("+") / max(len(stripped), 1)
    token_count = len(set(tokenize_text(stripped)))
    return alnum_count >= 20 and plus_ratio < 0.15 and token_count >= 3


def _split_sentences(text: str) -> List[str]:
    chunks = _SENTENCE_SPLIT_RE.split(text.strip())
    sentences = [_clean_sentence(chunk) for chunk in chunks if _clean_sentence(chunk)]
    if sentences:
        return sentences
    fallback = _clean_sentence(text)
    return [fallback] if fallback else []


def build_grounded_messages(question: str, chunks: Sequence[RetrievedChunk]) -> List[Dict[str, str]]:
    context_blocks = []
    for chunk in chunks:
        context_blocks.append(
            "\n".join(
                [
                    f"[{chunk.chunk_id}]",
                    f"doc_name={chunk.doc_name}",
                    f"page_start={chunk.page_start}",
                    f"page_end={chunk.page_end}",
                    f"section_title={chunk.section_title or '(none)'}",
                    f"text={chunk.text}",
                ]
            )
        )

    system_prompt = (
        "You are PaperLens, a grounded QA assistant. "
        "Answer only from the provided document chunks. "
        "Use the same language as the user's question when possible. "
        "If the context is not sufficient, say so explicitly and set answerable=false. "
        "Return strict JSON with keys: answerable, answer, cited_chunk_ids, failure_reason. "
        "cited_chunk_ids must only contain chunk ids from the provided context."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{question}",
            "Context chunks:",
            "\n\n".join(context_blocks),
            (
                "Return JSON only. Example:\n"
                '{"answerable": true, "answer": "...", "cited_chunk_ids": ["chunk_id"], "failure_reason": null}'
            ),
        ]
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


class AnswerService:
    def __init__(
        self,
        retriever: Retriever,
        settings: Settings,
        llm_client: Optional[Any] = None,
        max_citations: int = 3,
        fallback_sentence_count: int = 2,
    ) -> None:
        self.retriever = retriever
        self.settings = settings
        self.max_citations = max_citations
        self.fallback_sentence_count = fallback_sentence_count
        self.llm_client = llm_client if llm_client is not None else self._build_llm_client(settings)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        retriever: Optional[Retriever] = None,
        llm_client: Optional[Any] = None,
    ) -> "AnswerService":
        return cls(
            retriever=retriever or Retriever.from_settings(settings),
            settings=settings,
            llm_client=llm_client,
        )

    def answer_question(self, question: str, top_k: Optional[int] = None) -> AskResponse:
        default_top_k = getattr(self.retriever, "default_top_k", self.settings.top_k)
        requested_top_k = top_k or default_top_k
        search_top_k = max(requested_top_k, default_top_k * 4)
        # Allow the answer layer to consider slightly weaker retrieval candidates.
        # The fallback sentence selector still applies its own confidence filter,
        # but this prevents larger merged chunks from being discarded too early.
        search_score_threshold = min(self.settings.retrieval_score_threshold, 0.18)
        chunks, retrieval = self.retriever.retrieve(
            question,
            top_k=search_top_k,
            score_threshold=search_score_threshold,
        )
        retrieval.top_k = requested_top_k
        if not chunks:
            return self._refusal_response(
                question=question,
                retrieval=retrieval,
                failure_reason="insufficient_context",
            )

        draft = self._generate_draft(question, chunks)
        if draft.answerable:
            citations = self._map_citations(chunks, draft.cited_chunk_ids)
            if not citations:
                fallback_draft = self._fallback_draft(question, chunks)
                if not fallback_draft.answerable:
                    return self._refusal_response(
                        question=question,
                        retrieval=retrieval,
                        failure_reason=fallback_draft.failure_reason or "low_confidence",
                    )
                draft = fallback_draft
                citations = self._map_citations(chunks, draft.cited_chunk_ids)

            return AskResponse(
                question=question,
                answer=draft.answer,
                answerable=True,
                citations=citations[: self.max_citations],
                retrieval=retrieval,
                failure_reason=None,
            )

        return self._refusal_response(
            question=question,
            retrieval=retrieval,
            failure_reason=draft.failure_reason or "insufficient_context",
        )

    def _generate_draft(self, question: str, chunks: Sequence[RetrievedChunk]) -> AnswerDraft:
        if self.llm_client is not None and self.settings.llm_model:
            try:
                return self._llm_draft(question, chunks)
            except AnswerGenerationError:
                return self._fallback_draft(question, chunks)
        return self._fallback_draft(question, chunks)

    def _llm_draft(self, question: str, chunks: Sequence[RetrievedChunk]) -> AnswerDraft:
        messages = build_grounded_messages(question, chunks)
        try:
            response = self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                temperature=0.0,
                messages=messages,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise AnswerGenerationError(f"LLM answer generation failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise AnswerGenerationError("LLM response did not contain a valid message") from exc

        payload = self._parse_llm_payload(content)
        valid_chunk_ids = {chunk.chunk_id for chunk in chunks}
        cited_chunk_ids = [
            chunk_id
            for chunk_id in payload.get("cited_chunk_ids", [])
            if chunk_id in valid_chunk_ids
        ]

        answer = str(payload.get("answer", "")).strip()
        answerable = bool(payload.get("answerable", True))
        failure_reason = payload.get("failure_reason")

        if answerable and not answer:
            raise AnswerGenerationError("LLM answer payload was empty")

        return AnswerDraft(
            answer=answer if answerable else _default_refusal_answer(question),
            answerable=answerable,
            cited_chunk_ids=cited_chunk_ids,
            failure_reason=None if answerable else str(failure_reason or "insufficient_context"),
        )

    def _fallback_draft(self, question: str, chunks: Sequence[RetrievedChunk]) -> AnswerDraft:
        support_sentences = self._select_support_sentences(question, chunks)
        if not support_sentences:
            return AnswerDraft(
                answer=_default_refusal_answer(question),
                answerable=False,
                cited_chunk_ids=[],
                failure_reason="low_confidence",
            )

        selected_sentences = support_sentences[: self.fallback_sentence_count]
        answer_parts = [item.text for item in selected_sentences]
        cited_chunk_ids: List[str] = []
        for item in selected_sentences:
            if item.chunk.chunk_id not in cited_chunk_ids:
                cited_chunk_ids.append(item.chunk.chunk_id)

        if _contains_cjk(question):
            answer = "根据检索到的文档内容，相关证据显示：" + " ".join(answer_parts)
        else:
            answer = "Based on the retrieved evidence: " + " ".join(answer_parts)

        return AnswerDraft(
            answer=answer.strip(),
            answerable=True,
            cited_chunk_ids=cited_chunk_ids,
            failure_reason=None,
        )

    def _select_support_sentences(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
    ) -> List[_SupportSentence]:
        question_tokens = set(tokenize_text(question))
        question_anchors = set(extract_anchor_tokens(question))
        support_sentences: List[_SupportSentence] = []

        for rank, chunk in enumerate(chunks):
            for sentence in _split_sentences(chunk.text):
                if not _is_informative_sentence(sentence):
                    continue
                sentence_tokens = set(tokenize_text(sentence))
                overlap = len(question_tokens.intersection(sentence_tokens))
                anchor_overlap = len(question_anchors.intersection(sentence_tokens))
                support_score = (
                    chunk.score
                    + (0.14 * anchor_overlap)
                    + (0.03 * overlap)
                    - (0.01 * rank)
                )
                support_sentences.append(
                    _SupportSentence(
                        text=sentence,
                        chunk=chunk,
                        support_score=support_score,
                        overlap=overlap,
                        anchor_overlap=anchor_overlap,
                    )
                )

        support_sentences.sort(key=lambda item: item.support_score, reverse=True)
        if not support_sentences:
            return []

        best = support_sentences[0]
        if question_anchors:
            if best.anchor_overlap == 0 and best.support_score < 0.45:
                return []
        elif best.overlap == 0 and best.support_score < 0.45:
            return []

        if best.support_score < max(self.settings.retrieval_score_threshold, 0.18):
            return []

        unique_by_chunk: List[_SupportSentence] = []
        seen_chunk_ids = set()
        for item in support_sentences:
            if item.chunk.chunk_id in seen_chunk_ids:
                continue
            unique_by_chunk.append(item)
            seen_chunk_ids.add(item.chunk.chunk_id)
            if len(unique_by_chunk) >= self.fallback_sentence_count:
                break
        return unique_by_chunk

    def _map_citations(
        self,
        chunks: Sequence[RetrievedChunk],
        cited_chunk_ids: Sequence[str],
    ) -> List[Citation]:
        lookup = {chunk.chunk_id: chunk for chunk in chunks}
        citations: List[Citation] = []
        seen = set()

        for chunk_id in cited_chunk_ids:
            if chunk_id in seen or chunk_id not in lookup:
                continue
            citations.append(lookup[chunk_id].to_citation())
            seen.add(chunk_id)
            if len(citations) >= self.max_citations:
                return citations

        if citations:
            return citations

        for chunk in chunks:
            if chunk.chunk_id in seen:
                continue
            citations.append(chunk.to_citation())
            seen.add(chunk.chunk_id)
            if len(citations) >= self.max_citations:
                break
        return citations

    def _refusal_response(
        self,
        question: str,
        retrieval: RetrievalMetadata,
        failure_reason: str,
    ) -> AskResponse:
        return AskResponse(
            question=question,
            answer=_default_refusal_answer(question),
            answerable=False,
            citations=[],
            retrieval=retrieval,
            failure_reason=failure_reason,
        )

    @staticmethod
    def _parse_llm_payload(content: Any) -> Dict[str, Any]:
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            raise AnswerGenerationError("LLM response did not contain a JSON object")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AnswerGenerationError("LLM response JSON could not be parsed") from exc

    @staticmethod
    def _build_llm_client(settings: Settings) -> Optional[Any]:
        if not settings.llm_model:
            return None
        if not settings.openai_api_key:
            return None
        if OpenAI is None:
            raise LlmConfigurationError("openai is not installed in the active environment")

        client_kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        return OpenAI(**client_kwargs)
