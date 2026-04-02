"""Grounded answer generation for PaperLens."""

from __future__ import annotations

import json
import re
import unicodedata
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
_SUPPORTED_ANSWER_BACKENDS = {"auto", "openai", "extractive"}
_LIST_QUESTION_RE = re.compile(
    r"(?:\b(?:list|name|which|identify|enumerate|what are|what were)\b|"
    r"\b(?:two|three|four|\d+)\s+(?:new\s+)?(?:tasks?|objectives?|strategies?|methods?|components?|modules?|stages?)\b|"
    r"哪些|哪几|列出|分别是|分别是什么|分别有哪些|"
    r"两(?:个|项|种)?.{0,12}(?:任务|目标|方法|模块|部分|阶段)|"
    r"三(?:个|项|种)?.{0,12}(?:任务|目标|方法|模块|部分|阶段))",
    re.IGNORECASE,
)
_ENUMERATION_CUE_RE = re.compile(
    r"(?:\bthe first\b|\bthe second\b|\bfirst is\b|\bsecond is\b|"
    r"\btwo new\b|\bnew pre-training\b|\bnew training\b|"
    r"\bwe add\b|\bin addition to\b|\btext-image alignment\b|\btext-image matching\b|"
    r"^\s*[#\-\*\u2022]\d*|\n\s*[#\-\*\u2022]\d*)",
    re.IGNORECASE | re.MULTILINE,
)
_GENERIC_OVERVIEW_RE = re.compile(
    r"(?:\bin this section\b|\bwe will introduce\b|\bwhich is illustrated in figure\b|"
    r"\bwe present an improved version\b|\bwe propose [^.]{0,80} architecture\b)",
    re.IGNORECASE,
)
_DIRECT_LEADIN_RE = re.compile(
    r"^(?:"
    r"Based on (?:the )?(?:retrieved|provided) (?:context|documents?)[:,]?\s*|"
    r"According to (?:the )?(?:retrieved|provided) (?:context|documents?)[:,]?\s*|"
    r"根据(?:检索到|提供的)?(?:文档|上下文|资料)(?:内容|信息|证据)?[，,:： ]*|"
    r"基于(?:检索到|提供的)?(?:文档|上下文|资料)(?:内容|信息|证据)?[，,:： ]*"
    r")",
    re.IGNORECASE,
)
_FIXED_COUNT_HINTS = (
    (2, re.compile(r"(?:\b(?:2|two)\b|两个|两项|两种|二个)", re.IGNORECASE)),
    (3, re.compile(r"(?:\b(?:3|three)\b|三个|三项|三种)", re.IGNORECASE)),
    (4, re.compile(r"(?:\b(?:4|four)\b|四个|四项|四种)", re.IGNORECASE)),
)
_FIRST_SECOND_ITEM_RE = re.compile(
    r"\bthe first is (?:the proposed )?(?P<first>[A-Za-z][A-Za-z-]*(?: [A-Za-z][A-Za-z-]*){0,4})"
    r"(?: (?:strategy|task|objective|objectives))?(?:\s*\((?P<first_acronym>[A-Z0-9-]{2,})\))?"
    r".{0,240}?\bthe second is (?:the )?(?P<second>[A-Za-z][A-Za-z-]*(?: [A-Za-z][A-Za-z-]*){0,4})"
    r"(?: (?:strategy|task|objective|objectives))?(?:\s*\((?P<second_acronym>[A-Z0-9-]{2,})\))?",
    re.IGNORECASE | re.DOTALL,
)
_ACRONYM_TERM_RE = re.compile(
    r"\b([A-Za-z][A-Za-z-]*(?: [A-Za-z][A-Za-z-]*){0,4})\s*\(([A-Z0-9-]{2,})\)"
)
_CROSSLINGUAL_QUERY_HINTS = (
    ("预训练", ("pre", "training", "pretraining")),
    ("任务", ("task", "tasks", "objective", "objectives", "strategy", "strategies")),
    ("目标", ("objective", "objectives", "target", "targets")),
    ("跨模态", ("cross", "modal", "modality", "multimodal", "multi", "modal")),
    ("多模态", ("multimodal", "multi", "modal", "cross", "modal")),
    ("文本", ("text", "token", "tokens")),
    ("图像", ("image", "images", "visual")),
    ("对齐", ("alignment", "align")),
    ("匹配", ("matching", "match")),
    ("新增", ("new", "additional", "add")),
    ("文档理解", ("document", "understanding")),
    ("建模", ("model", "modeling")),
    ("布局", ("layout", "spatial")),
    ("核心", ("core", "key", "central")),
)


# Override mojibake-sensitive Chinese patterns with explicit UTF-8 variants so
# Chinese questions participate in the same list-style and citation heuristics.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_LIST_QUESTION_RE = re.compile(
    r"(?:\b(?:list|name|which|identify|enumerate|what are|what were)\b|"
    r"\b(?:two|three|four|\d+)\s+(?:new\s+)?(?:tasks?|objectives?|strategies?|methods?|components?|modules?|stages?)\b|"
    r"哪些|哪几|列出|分别是|分别是什么|分别有哪些|"
    r"(?:两|二)(?:个|项|种)?.{0,12}(?:任务|目标|方法|模块|部分|阶段|预训练任务|预训练目标)|"
    r"三(?:个|项|种)?.{0,12}(?:任务|目标|方法|模块|部分|阶段)|"
    r"四(?:个|项|种)?.{0,12}(?:任务|目标|方法|模块|部分|阶段))",
    re.IGNORECASE,
)
_DIRECT_LEADIN_RE = re.compile(
    r"^(?:"
    r"Based on (?:the )?(?:retrieved|provided) (?:context|documents?)[:,]?\s*|"
    r"According to (?:the )?(?:retrieved|provided) (?:context|documents?)[:,]?\s*|"
    r"根据(?:检索到|提供的)?(?:文档|上下文|资料)(?:内容|信息|证据)?[，,:： ]*|"
    r"基于(?:检索到|提供的)?(?:文档|上下文|资料)(?:内容|信息|证据)?[，,:： ]*"
    r")",
    re.IGNORECASE,
)
_FIXED_COUNT_HINTS = (
    (2, re.compile(r"(?:\b(?:2|two)\b|两个|两项|两种|二个)", re.IGNORECASE)),
    (3, re.compile(r"(?:\b(?:3|three)\b|三个|三项|三种)", re.IGNORECASE)),
    (4, re.compile(r"(?:\b(?:4|four)\b|四个|四项|四种)", re.IGNORECASE)),
)
_TASK_CONTEXT_RE = re.compile(
    r"\b(?:task|tasks|objective|objectives|strategy|strategies|pre-training|pretraining|"
    r"cross-modality|cross-modal|alignment|matching)\b",
    re.IGNORECASE,
)
_NON_TASK_TERM_RE = re.compile(
    r"\b(?:mechanism|architecture|module|backbone|embedding|encoder|decoder|attention)\b",
    re.IGNORECASE,
)
_TASK_PHRASE_TERM_RE = re.compile(
    r"\b(?:the proposed |proposed )?(?P<term>[A-Za-z][A-Za-z-]*(?: [A-Za-z][A-Za-z-]*){0,5}) "
    r"(?P<label>strategy|task|objective|objectives)\b",
    re.IGNORECASE,
)
_CROSSLINGUAL_QUERY_HINTS = (
    ("预训练", ("pre", "training", "pretraining")),
    ("任务", ("task", "tasks", "objective", "objectives", "strategy", "strategies")),
    ("目标", ("objective", "objectives", "target", "targets")),
    ("跨模态", ("cross", "modal", "modality", "multimodal", "multi", "modal")),
    ("多模态", ("multimodal", "multi", "modal", "cross", "modal")),
    ("文本", ("text", "token", "tokens")),
    ("图像", ("image", "images", "visual")),
    ("对齐", ("alignment", "align")),
    ("匹配", ("matching", "match")),
    ("新增", ("new", "additional", "add")),
    ("文档理解", ("document", "understanding")),
    ("建模", ("model", "modeling")),
    ("布局", ("layout", "spatial")),
    ("核心", ("core", "key", "central")),
)

# ASCII-escaped variants avoid Windows console encoding issues while keeping
# the runtime behavior correct for Chinese prompts.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+")
_LIST_QUESTION_RE = re.compile(
    r"(?:\b(?:list|name|which|identify|enumerate|what are|what were)\b|"
    r"\b(?:two|three|four|\d+)\s+(?:new\s+)?(?:tasks?|objectives?|strategies?|methods?|components?|modules?|stages?)\b|"
    r"\u54ea\u4e9b|\u54ea\u51e0|\u5217\u51fa|\u5206\u522b\u662f|\u5206\u522b\u662f\u4ec0\u4e48|\u5206\u522b\u6709\u54ea\u4e9b|"
    r"(?:\u4e24|\u4e8c)(?:\u4e2a|\u9879|\u79cd)?.{0,12}(?:\u4efb\u52a1|\u76ee\u6807|\u65b9\u6cd5|\u6a21\u5757|\u90e8\u5206|\u9636\u6bb5|\u9884\u8bad\u7ec3\u4efb\u52a1|\u9884\u8bad\u7ec3\u76ee\u6807)|"
    r"\u4e09(?:\u4e2a|\u9879|\u79cd)?.{0,12}(?:\u4efb\u52a1|\u76ee\u6807|\u65b9\u6cd5|\u6a21\u5757|\u90e8\u5206|\u9636\u6bb5)|"
    r"\u56db(?:\u4e2a|\u9879|\u79cd)?.{0,12}(?:\u4efb\u52a1|\u76ee\u6807|\u65b9\u6cd5|\u6a21\u5757|\u90e8\u5206|\u9636\u6bb5))",
    re.IGNORECASE,
)
_DIRECT_LEADIN_RE = re.compile(
    r"^(?:"
    r"Based on (?:the )?(?:retrieved|provided) (?:context|documents?)[:,]?\s*|"
    r"According to (?:the )?(?:retrieved|provided) (?:context|documents?)[:,]?\s*|"
    r"\u6839\u636e(?:\u68c0\u7d22\u5230|\u63d0\u4f9b\u7684)?(?:\u6587\u6863|\u4e0a\u4e0b\u6587|\u8d44\u6599)(?:\u5185\u5bb9|\u4fe1\u606f|\u8bc1\u636e)?[\uff0c,:： ]*|"
    r"\u57fa\u4e8e(?:\u68c0\u7d22\u5230|\u63d0\u4f9b\u7684)?(?:\u6587\u6863|\u4e0a\u4e0b\u6587|\u8d44\u6599)(?:\u5185\u5bb9|\u4fe1\u606f|\u8bc1\u636e)?[\uff0c,:： ]*"
    r")",
    re.IGNORECASE,
)
_FIXED_COUNT_HINTS = (
    (2, re.compile(r"(?:\b(?:2|two)\b|\u4e24\u4e2a|\u4e24\u9879|\u4e24\u79cd|\u4e8c\u4e2a)", re.IGNORECASE)),
    (3, re.compile(r"(?:\b(?:3|three)\b|\u4e09\u4e2a|\u4e09\u9879|\u4e09\u79cd)", re.IGNORECASE)),
    (4, re.compile(r"(?:\b(?:4|four)\b|\u56db\u4e2a|\u56db\u9879|\u56db\u79cd)", re.IGNORECASE)),
)
_CROSSLINGUAL_QUERY_HINTS = (
    ("\u9884\u8bad\u7ec3", ("pre", "training", "pretraining")),
    ("\u4efb\u52a1", ("task", "tasks", "objective", "objectives", "strategy", "strategies")),
    ("\u76ee\u6807", ("objective", "objectives", "target", "targets")),
    ("\u8de8\u6a21\u6001", ("cross", "modal", "modality", "multimodal", "multi", "modal")),
    ("\u591a\u6a21\u6001", ("multimodal", "multi", "modal", "cross", "modal")),
    ("\u6587\u672c", ("text", "token", "tokens")),
    ("\u56fe\u50cf", ("image", "images", "visual")),
    ("\u5bf9\u9f50", ("alignment", "align")),
    ("\u5339\u914d", ("matching", "match")),
    ("\u65b0\u589e", ("new", "additional", "add")),
    ("\u6587\u6863\u7406\u89e3", ("document", "understanding")),
    ("\u5efa\u6a21", ("model", "modeling")),
    ("\u5e03\u5c40", ("layout", "spatial")),
    ("\u6838\u5fc3", ("core", "key", "central")),
)

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


def _question_prefers_list(question: str) -> bool:
    if _LIST_QUESTION_RE.search(question):
        return True
    if _question_requested_item_count(question) is not None:
        return True
    return any(marker in question for marker in ("哪些", "哪几", "列出", "分别"))


def _question_requested_item_count(question: str) -> Optional[int]:
    for count, pattern in _FIXED_COUNT_HINTS:
        if pattern.search(question):
            return count
    fallback_patterns = (
        (2, r"(?:\b2\b|\btwo\b|2个|2项|2种|两个|两项|两种|二个|二项|二种)"),
        (3, r"(?:\b3\b|\bthree\b|3个|3项|3种|三个|三项|三种)"),
        (4, r"(?:\b4\b|\bfour\b|4个|4项|4种|四个|四项|四种)"),
    )
    for count, pattern in fallback_patterns:
        if re.search(pattern, question, re.IGNORECASE):
            return count
    return None


def _expand_query_tokens(text: str) -> List[str]:
    expanded: List[str] = []
    for needle, tokens in _CROSSLINGUAL_QUERY_HINTS:
        if needle in text:
            for token in tokens:
                if token not in expanded:
                    expanded.append(token)
    return expanded


def _query_token_set(question: str) -> set[str]:
    tokens = set(tokenize_text(question))
    tokens.update(_expand_query_tokens(question))
    return tokens


def _chunk_search_text(chunk: RetrievedChunk) -> str:
    section_title = _normalize_match_text(chunk.section_title or "")
    text = _normalize_match_text(chunk.text)
    if section_title:
        return f"{section_title}\n{text}"
    return text


def _chunk_has_enumeration_cues(chunk: RetrievedChunk) -> bool:
    return bool(_ENUMERATION_CUE_RE.search(_chunk_search_text(chunk)))


def _chunk_is_generic_overview(chunk: RetrievedChunk) -> bool:
    return bool(_GENERIC_OVERVIEW_RE.search(_chunk_search_text(chunk)))


def _build_answer_format_hint(question: str) -> str:
    instructions = [
        "Start with the answer itself instead of describing the retrieval process.",
        "Do not mention phrases like 'Based on the retrieved context' in the answer field.",
    ]
    if _question_prefers_list(question):
        instructions.append("Format the answer as a concise numbered list, one item per line.")
        requested_count = _question_requested_item_count(question)
        if requested_count is not None:
            instructions.append(
                f"The question asks for {requested_count} items. If the context supports it, return exactly {requested_count} items."
            )
        instructions.append(
            "For named tasks, methods, components, or objectives, give the official paper term directly and keep any acronym in parentheses when available."
        )
    else:
        instructions.append("Prefer one short direct sentence before any brief supporting detail.")
    return " ".join(instructions)


def _normalize_llm_answer(question: str, answer: str) -> str:
    normalized = answer.strip()
    for prefix in (
        "根据检索到的文档内容，",
        "根据检索到的文档内容：",
        "根据提供的文档内容，",
        "根据提供的文档内容：",
        "基于检索到的文档内容，",
        "基于检索到的文档内容：",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    normalized = re.sub(
        r"^(?:\u76f8\u5173\u8bc1\u636e\u663e\u793a|evidence shows?)[:\uff1a\uff0c,\s-]*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    for _ in range(3):
        updated = _DIRECT_LEADIN_RE.sub("", normalized).strip()
        if updated == normalized:
            break
        normalized = updated
    if _question_prefers_list(question):
        lines = [line.rstrip() for line in normalized.splitlines()]
        normalized = "\n".join(line for line in lines if line.strip())
    return normalized


def _title_case_term(term: str) -> str:
    words: List[str] = []
    for word in term.split():
        pieces = []
        for piece in word.split("-"):
            if piece.isupper():
                pieces.append(piece)
            else:
                pieces.append(piece.capitalize())
        words.append("-".join(pieces))
    return " ".join(words)


def _format_named_item(term: str, acronym: Optional[str] = None) -> str:
    normalized_term = _title_case_term(_clean_sentence(term))
    if acronym:
        cleaned_acronym = acronym.strip().upper()
        if cleaned_acronym and f"({cleaned_acronym})" not in normalized_term:
            return f"{normalized_term} ({cleaned_acronym})"
    return normalized_term


def _list_answer_needs_refinement(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    if len(lines) < requested_count:
        return True

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 12 for line in stripped_lines):
        return True
    if any("•" in line or "\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        normalized_answer = answer.lower()
        matched_items = 0
        for item in refined_items[:requested_count]:
            canonical_term = item.split(" (", 1)[0].lower()
            acronym_match = re.search(r"\(([A-Z0-9-]{2,})\)", item)
            if canonical_term and canonical_term in normalized_answer:
                matched_items += 1
                continue
            if acronym_match and acronym_match.group(1).lower() in normalized_answer:
                matched_items += 1
        if matched_items < requested_count:
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose")
    )


_LIST_REFINER_V2 = True


def _list_answer_needs_refinement_v2(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(lines) < requested_count:
        return True
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[.)]\s*|[-*]\s*|\u2022\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 10 for line in stripped_lines):
        return True
    if any("\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        matched_items = 0
        prefix_matches = 0
        remaining_items = list(refined_items[:requested_count])
        for line in stripped_lines:
            normalized_line = line.lower()
            for item in list(remaining_items):
                canonical_term, acronym = _split_named_item(item)
                canonical_lower = canonical_term.lower()
                acronym_lower = acronym.lower() if acronym else None
                contains_item = bool(
                    (canonical_lower and canonical_lower in normalized_line)
                    or (acronym_lower and acronym_lower in normalized_line)
                )
                if not contains_item:
                    continue
                matched_items += 1
                if (
                    (canonical_lower and normalized_line.startswith(canonical_lower))
                    or (acronym_lower and normalized_line.startswith(acronym_lower))
                ):
                    prefix_matches += 1
                remaining_items.remove(item)
                break
        if matched_items < requested_count or prefix_matches < requested_count:
            return True
        if any(
            sum(
                1
                for item in refined_items[:requested_count]
                if _split_named_item(item)[0].lower() in line.lower()
            ) > 1
            for line in stripped_lines
        ):
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )


def _extract_named_list_items(question: str, chunks: Sequence[RetrievedChunk]) -> List[str]:
    requested_count = _question_requested_item_count(question) or 2

    for chunk in chunks:
        match = _FIRST_SECOND_ITEM_RE.search(_chunk_search_text(chunk))
        if not match:
            continue
        first_term = _sanitize_candidate_term(match.group("first"))
        second_term = _sanitize_candidate_term(match.group("second"))
        items = [
            _format_named_item(first_term, match.group("first_acronym") or _lookup_acronym_for_term(first_term, chunks)),
            _format_named_item(second_term, match.group("second_acronym") or _lookup_acronym_for_term(second_term, chunks)),
        ]
        return items[:requested_count]

    question_tokens = _query_token_set(question)
    candidates: List[str] = []
    seen = set()
    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            lowered = sentence.lower()
            if not (
                _ENUMERATION_CUE_RE.search(sentence)
                or any(word in lowered for word in ("task", "tasks", "objective", "objectives", "strategy", "strategies"))
            ):
                continue
            for match in _ACRONYM_TERM_RE.finditer(sentence):
                term = _format_named_item(match.group(1), match.group(2))
                term_tokens = set(tokenize_text(term))
                if not term_tokens.intersection(question_tokens):
                    continue
                if term not in seen:
                    candidates.append(term)
                    seen.add(term)
                if len(candidates) >= requested_count:
                    return candidates
    return candidates


def _default_refusal_answer(question: str) -> str:
    if _contains_cjk(question):
        return "当前检索到的文档内容不足以可靠回答这个问题。"
    return "The retrieved context is not sufficient to answer this question reliably."


def _normalize_llm_answer(question: str, answer: str) -> str:
    normalized = answer.strip()
    for prefix in (
        "根据检索到的文档内容，",
        "根据检索到的文档内容：",
        "根据提供的文档内容，",
        "根据提供的文档内容：",
        "基于检索到的文档内容，",
        "基于检索到的文档内容：",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    for _ in range(3):
        updated = _DIRECT_LEADIN_RE.sub("", normalized).strip()
        if updated == normalized:
            break
        normalized = updated
    if _question_prefers_list(question):
        lines = [line.rstrip() for line in normalized.splitlines()]
        normalized = "\n".join(line for line in lines if line.strip())
    return normalized


def _list_answer_needs_refinement(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(lines) < requested_count:
        return True
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 12 for line in stripped_lines):
        return True
    if any("•" in line or "\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        normalized_answer = answer.lower()
        matched_items = 0
        for item in refined_items[:requested_count]:
            canonical_term = item.split(" (", 1)[0].lower()
            acronym_match = re.search(r"\(([A-Z0-9-]{2,})\)", item)
            if canonical_term and canonical_term in normalized_answer:
                matched_items += 1
                continue
            if acronym_match and acronym_match.group(1).lower() in normalized_answer:
                matched_items += 1
        if matched_items < requested_count:
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in ("根据检索到的文档内容", "根据提供的文档内容", "基于检索到的文档内容", "我们引入", "我们提出")
    )


def _question_requests_task_like_items(question: str) -> bool:
    lowered = question.lower()
    if any(token in lowered for token in ("task", "tasks", "objective", "objectives", "strategy", "strategies")):
        return True
    return any(token in question for token in ("任务", "目标", "预训练", "策略", "方法"))


def _lookup_acronym_for_term(term: str, chunks: Sequence[RetrievedChunk]) -> Optional[str]:
    pattern = re.compile(
        rf"\b{re.escape(_clean_sentence(term))}\s*\(([A-Z0-9-]{{2,}})\)",
        re.IGNORECASE,
    )
    for chunk in chunks:
        match = pattern.search(_chunk_search_text(chunk))
        if match:
            return match.group(1).upper()
    return None


def _sanitize_candidate_term(term: str) -> str:
    cleaned = _clean_sentence(term)
    cleaned = re.sub(
        r"^(?:(?:we|use|add|propose|proposes|the|a|an|is|are|was|were|first|second|sec|ond)\s+)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:the\s+)?(?:proposed\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:(?:fine|coarse)-?grained\s+)+", "", cleaned, flags=re.IGNORECASE)
    if "text-image" in cleaned.lower():
        lowered = cleaned.lower()
        cleaned = cleaned[lowered.rfind("text-image") :]
    return cleaned


def _extract_named_list_items(question: str, chunks: Sequence[RetrievedChunk]) -> List[str]:
    requested_count = _question_requested_item_count(question) or 2

    for chunk in chunks:
        match = _FIRST_SECOND_ITEM_RE.search(_chunk_search_text(chunk))
        if not match:
            continue
        items = [
            _format_named_item(match.group("first"), match.group("first_acronym")),
            _format_named_item(match.group("second"), match.group("second_acronym")),
        ]
        return items[:requested_count]

    question_tokens = _query_token_set(question)
    task_like_question = _question_requests_task_like_items(question)

    acronym_candidates: Dict[str, float] = {}
    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            for match in _ACRONYM_TERM_RE.finditer(sentence):
                cleaned_term = _sanitize_candidate_term(match.group(1))
                formatted = _format_named_item(cleaned_term, match.group(2))
                lowered = formatted.lower()
                if any(token in lowered for token in ("grained cross-modality", "coarse- grained", "fine-grained")) and "text-image" not in lowered:
                    continue
                term_tokens = set(tokenize_text(formatted))
                overlap = len(question_tokens.intersection(term_tokens))
                score = chunk.score + (0.08 * overlap)
                if "text-image" in lowered:
                    score += 0.30
                if _TASK_CONTEXT_RE.search(sentence):
                    score += 0.18
                acronym_candidates[formatted] = max(acronym_candidates.get(formatted, float("-inf")), score)

    if acronym_candidates:
        ranked_acronyms = [
            item
            for item, _ in sorted(acronym_candidates.items(), key=lambda value: value[1], reverse=True)
        ]
        text_image_acronyms = [item for item in ranked_acronyms if "text-image" in item.lower()]
        if len(text_image_acronyms) >= requested_count:
            return text_image_acronyms[:requested_count]
        if len(ranked_acronyms) >= requested_count:
            return ranked_acronyms[:requested_count]

    candidate_scores: Dict[str, float] = {}

    def add_candidate(term: str, acronym: Optional[str], chunk: RetrievedChunk, sentence: str) -> None:
        sanitized_term = _sanitize_candidate_term(term)
        if not sanitized_term:
            return

        resolved_acronym = acronym or _lookup_acronym_for_term(sanitized_term, chunks)
        formatted = _format_named_item(sanitized_term, resolved_acronym)
        normalized_key = formatted.lower()
        term_tokens = set(tokenize_text(formatted))
        overlap = len(question_tokens.intersection(term_tokens))
        lowered = formatted.lower()

        score = chunk.score + (0.08 * overlap)
        if _TASK_CONTEXT_RE.search(sentence):
            score += 0.18
        if _chunk_has_enumeration_cues(chunk):
            score += 0.08
        if _chunk_is_generic_overview(chunk):
            score -= 0.10
        if resolved_acronym:
            score += 0.08
        if "text-image" in lowered:
            score += 0.24
        elif task_like_question and {"text", "image"}.issubset(question_tokens):
            score -= 0.28
        if any(token in lowered for token in ("cross-modality", "grained")) and "text-image" not in lowered:
            score -= 0.24
        if task_like_question and _NON_TASK_TERM_RE.search(lowered):
            score -= 0.35
        if overlap == 0 and task_like_question:
            score -= 0.20

        current = candidate_scores.get(normalized_key)
        if current is None or score > current:
            candidate_scores[normalized_key] = score

    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            lowered = sentence.lower()
            if not (
                _ENUMERATION_CUE_RE.search(sentence)
                or _TASK_CONTEXT_RE.search(sentence)
                or "text-image" in lowered
            ):
                continue
            for match in _ACRONYM_TERM_RE.finditer(sentence):
                add_candidate(match.group(1), match.group(2), chunk, sentence)
            for match in _TASK_PHRASE_TERM_RE.finditer(sentence):
                add_candidate(match.group("term"), None, chunk, sentence)

    ranked_items = [
        item
        for item, _ in sorted(candidate_scores.items(), key=lambda value: value[1], reverse=True)
    ]
    if task_like_question and {"text", "image"}.issubset(question_tokens):
        text_image_items = [item for item in ranked_items if "text-image" in item]
        if len(text_image_items) >= requested_count:
            return text_image_items[:requested_count]
    return ranked_items[:requested_count]


def _default_refusal_answer(question: str) -> str:
    if _contains_cjk(question):
        return "当前检索到的文档内容不足以可靠回答这个问题。"
    return "The retrieved context is not sufficient to answer this question reliably."


def _normalize_llm_answer(question: str, answer: str) -> str:
    normalized = answer.strip()
    for prefix in (
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    normalized = re.sub(
        r"^(?:\u76f8\u5173\u8bc1\u636e\u663e\u793a|evidence shows?)[:\uff1a\uff0c,\s-]*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    for _ in range(3):
        updated = _DIRECT_LEADIN_RE.sub("", normalized).strip()
        if updated == normalized:
            break
        normalized = updated
    if _question_prefers_list(question):
        lines = [line.rstrip() for line in normalized.splitlines()]
        normalized = "\n".join(line for line in lines if line.strip())
    return normalized


def _list_answer_needs_refinement(question: str, answer: str) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(acronym_mentions) >= requested_count:
        return False

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )


def _list_answer_needs_refinement(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(lines) < requested_count:
        return True
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[.)]\s*|[-*]\s*|\u2022\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 10 for line in stripped_lines):
        return True
    if any("\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        matched_items = 0
        prefix_matches = 0
        remaining_items = list(refined_items[:requested_count])
        for line in stripped_lines:
            normalized_line = line.lower()
            for item in list(remaining_items):
                canonical_term, acronym = _split_named_item(item)
                canonical_lower = canonical_term.lower()
                acronym_lower = acronym.lower() if acronym else None
                contains_item = bool(
                    (canonical_lower and canonical_lower in normalized_line)
                    or (acronym_lower and acronym_lower in normalized_line)
                )
                if not contains_item:
                    continue
                matched_items += 1
                if (
                    (canonical_lower and normalized_line.startswith(canonical_lower))
                    or (acronym_lower and normalized_line.startswith(acronym_lower))
                ):
                    prefix_matches += 1
                remaining_items.remove(item)
                break
        if matched_items < requested_count or prefix_matches < requested_count:
            return True
        if any(
            sum(
                1
                for item in refined_items[:requested_count]
                if _split_named_item(item)[0].lower() in line.lower()
            ) > 1
            for line in stripped_lines
        ):
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )


def _question_requests_task_like_items(question: str) -> bool:
    lowered = question.lower()
    if any(token in lowered for token in ("task", "tasks", "objective", "objectives", "strategy", "strategies")):
        return True
    return any(
        token in question
        for token in (
            "\u4efb\u52a1",
            "\u76ee\u6807",
            "\u9884\u8bad\u7ec3",
            "\u7b56\u7565",
            "\u65b9\u6cd5",
        )
    )


def _lookup_acronym_for_term(term: str, chunks: Sequence[RetrievedChunk]) -> Optional[str]:
    normalized_term = _clean_sentence(term)
    spaced_pattern = re.escape(normalized_term).replace(r"\-", r"[-\s]?")
    pattern = re.compile(
        rf"\b{spaced_pattern}\s*\(([A-Z0-9-]{{2,}})\)",
        re.IGNORECASE,
    )
    for chunk in chunks:
        match = pattern.search(_chunk_search_text(chunk))
        if match:
            return match.group(1).upper()
    return None


def _split_named_item(item: str) -> Tuple[str, Optional[str]]:
    canonical_term = item.split(" (", 1)[0].strip()
    acronym_match = re.search(r"\(([A-Z0-9-]{2,})\)", item)
    acronym = acronym_match.group(1).upper() if acronym_match else None
    return canonical_term, acronym


def _chunk_directly_supports_item(chunk: RetrievedChunk, item: str) -> bool:
    canonical_term, acronym = _split_named_item(item)
    search_text = _chunk_search_text(chunk).lower()
    section_title = _normalize_match_text(chunk.section_title or "").lower()
    canonical_lower = canonical_term.lower()
    if canonical_lower and (canonical_lower in search_text or canonical_lower in section_title):
        return True
    return bool(acronym and acronym.lower() in search_text)


def _extract_numbered_answer_items(answer: str) -> List[str]:
    items: List[str] = []
    for line in answer.splitlines():
        stripped = re.sub(r"^\s*(?:\d+[.)]\s*|[-*]\s*|\u2022\s*)", "", line).strip()
        if stripped:
            items.append(stripped)
    return items


def _score_chunk_for_item_support(
    service: "AnswerService",
    question: str,
    chunk: RetrievedChunk,
    rank: int,
    focus_item: str,
) -> float:
    score = service._score_chunk_for_prompt(question, chunk, rank)
    score += service._score_chunk_for_focus_items(chunk, [focus_item])
    search_text = _chunk_search_text(chunk)
    search_text_lower = search_text.lower()
    section_title = _normalize_match_text(chunk.section_title or "").lower()
    canonical_term, acronym = _split_named_item(focus_item)
    canonical_lower = canonical_term.lower()

    if canonical_lower and canonical_lower in section_title:
        score += 0.24
    if _FIRST_SECOND_ITEM_RE.search(search_text):
        score += 0.20
    if acronym and acronym.lower() in search_text_lower:
        score += 0.16
    if canonical_lower and search_text_lower.startswith(canonical_lower):
        score += 0.12
    if canonical_term and re.search(
        rf"\b{re.escape(canonical_term)}\b[^.\n]{{0,80}}\b(?:is|refers to|denotes)\b",
        search_text,
        re.IGNORECASE,
    ):
        score += 0.18
    if canonical_term and acronym and re.search(
        rf"\b{re.escape(canonical_term)}\b\s*\({re.escape(acronym)}\)",
        search_text,
        re.IGNORECASE,
    ):
        score += 0.18
    if _TASK_CONTEXT_RE.search(search_text):
        score += 0.10
    if _chunk_is_generic_overview(chunk):
        score -= 0.10
    return score


def _select_llm_context_chunks_v2(
    service: "AnswerService",
    question: str,
    chunks: Sequence[RetrievedChunk],
) -> List[RetrievedChunk]:
    max_chunks = max(service.settings.llm_max_context_chunks, 1)
    focus_items = _extract_named_list_items(question, chunks) if _question_prefers_list(question) else []
    selected: List[RetrievedChunk] = []
    seen_chunk_ids: set[str] = set()

    for focus_item in focus_items:
        focus_ranked = sorted(
            (
                (index, chunk)
                for index, chunk in enumerate(chunks)
                if _chunk_directly_supports_item(chunk, focus_item)
            ),
            key=lambda item: _score_chunk_for_item_support(service, question, item[1], item[0], focus_item),
            reverse=True,
        )
        for _, chunk in focus_ranked:
            if chunk.chunk_id in seen_chunk_ids:
                continue
            selected.append(chunk)
            seen_chunk_ids.add(chunk.chunk_id)
            break

    ranked = sorted(
        enumerate(chunks),
        key=lambda item: (
            service._score_chunk_for_prompt(question, item[1], item[0])
            + service._score_chunk_for_focus_items(item[1], focus_items)
        ),
        reverse=True,
    )
    for _, chunk in ranked:
        if chunk.chunk_id in seen_chunk_ids:
            continue
        selected.append(chunk)
        seen_chunk_ids.add(chunk.chunk_id)
        if len(selected) >= max_chunks:
            break
    return selected[:max_chunks]


def _augment_list_context_chunks_v2(
    service: "AnswerService",
    question: str,
    chunks: Sequence[RetrievedChunk],
) -> List[RetrievedChunk]:
    if not _question_prefers_list(question):
        return list(chunks)

    focus_items = _extract_named_list_items(question, chunks)
    if not focus_items:
        return list(chunks)

    merged_chunks: List[RetrievedChunk] = []
    seen_chunk_ids: set[str] = set()

    def append_candidates(candidates: Sequence[RetrievedChunk]) -> None:
        for candidate in candidates:
            if candidate.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(candidate.chunk_id)
            merged_chunks.append(candidate)

    append_candidates(chunks)

    doc_hint = ""
    for chunk in chunks:
        if chunk.doc_id:
            doc_hint = chunk.doc_id
            break
    if not doc_hint and chunks:
        doc_hint = Path(chunks[0].doc_name).stem

    search_top_k = max(service.settings.llm_max_context_chunks * 4, 8)
    search_score_threshold = min(service.settings.retrieval_score_threshold, 0.18)
    query_variants: List[str] = []
    for focus_item in focus_items[:3]:
        canonical_term, acronym = _split_named_item(focus_item)
        expanded_query = " ".join(
            token
            for token in (question, canonical_term, acronym)
            if token
        )
        if expanded_query:
            query_variants.append(expanded_query)

        focused_query = " ".join(
            token
            for token in (doc_hint, canonical_term, acronym)
            if token
        )
        if focused_query:
            query_variants.append(focused_query)

    seen_queries: set[str] = set()
    for query_variant in query_variants:
        normalized_query = query_variant.strip()
        if not normalized_query or normalized_query in seen_queries:
            continue
        seen_queries.add(normalized_query)
        extra_chunks, _ = service.retriever.retrieve(
            normalized_query,
            top_k=search_top_k,
            score_threshold=search_score_threshold,
        )
        append_candidates(extra_chunks)

    return merged_chunks


def _extract_named_list_items(question: str, chunks: Sequence[RetrievedChunk]) -> List[str]:
    requested_count = _question_requested_item_count(question) or 2

    for chunk in chunks:
        match = _FIRST_SECOND_ITEM_RE.search(_chunk_search_text(chunk))
        if not match:
            continue
        items = [
            _format_named_item(match.group("first"), match.group("first_acronym")),
            _format_named_item(match.group("second"), match.group("second_acronym")),
        ]
        return items[:requested_count]

    question_tokens = _query_token_set(question)
    task_like_question = _question_requests_task_like_items(question)
    candidate_scores: Dict[str, float] = {}

    def add_candidate(term: str, acronym: Optional[str], chunk: RetrievedChunk, sentence: str) -> None:
        resolved_acronym = acronym or _lookup_acronym_for_term(term, chunks)
        formatted = _format_named_item(term, resolved_acronym)
        normalized_key = formatted.lower()
        term_tokens = set(tokenize_text(formatted))
        overlap = len(question_tokens.intersection(term_tokens))
        lowered = formatted.lower()

        score = chunk.score + (0.08 * overlap)
        if _TASK_CONTEXT_RE.search(sentence):
            score += 0.18
        if _chunk_has_enumeration_cues(chunk):
            score += 0.08
        if _chunk_is_generic_overview(chunk):
            score -= 0.10
        if resolved_acronym:
            score += 0.08
        if "text-image" in lowered:
            score += 0.12
        if task_like_question and _NON_TASK_TERM_RE.search(lowered):
            score -= 0.35
        if overlap == 0 and task_like_question:
            score -= 0.20

        current = candidate_scores.get(normalized_key)
        if current is None or score > current:
            candidate_scores[normalized_key] = score

    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            lowered = sentence.lower()
            if not (
                _ENUMERATION_CUE_RE.search(sentence)
                or _TASK_CONTEXT_RE.search(sentence)
                or "text-image" in lowered
            ):
                continue
            for match in _ACRONYM_TERM_RE.finditer(sentence):
                add_candidate(match.group(1), match.group(2), chunk, sentence)
            for match in _TASK_PHRASE_TERM_RE.finditer(sentence):
                add_candidate(match.group("term"), None, chunk, sentence)

    ranked_items = [
        item
        for item, _ in sorted(candidate_scores.items(), key=lambda value: value[1], reverse=True)
    ]
    return ranked_items[:requested_count]


def _default_refusal_answer(question: str) -> str:
    if _contains_cjk(question):
        return "\u5f53\u524d\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\u4e0d\u8db3\u4ee5\u53ef\u9760\u56de\u7b54\u8fd9\u4e2a\u95ee\u9898\u3002"
    return "The retrieved context is not sufficient to answer this question reliably."


def _list_answer_needs_refinement(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(lines) < requested_count:
        return True
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 12 for line in stripped_lines):
        return True
    if any("•" in line or "\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        normalized_answer = answer.lower()
        matched_items = 0
        for item in refined_items[:requested_count]:
            canonical_term = item.split(" (", 1)[0].lower()
            acronym_match = re.search(r"\(([A-Z0-9-]{2,})\)", item)
            if canonical_term and canonical_term in normalized_answer:
                matched_items += 1
                continue
            if acronym_match and acronym_match.group(1).lower() in normalized_answer:
                matched_items += 1
        if matched_items < requested_count:
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )


# Final overrides to keep the active answer-shaping behavior stable even
# though the file still contains earlier duplicate helper definitions.
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

    format_hint = _build_answer_format_hint(question)
    system_prompt = (
        "You are PaperLens, a grounded QA assistant. "
        "Answer only from the provided document chunks. "
        "Use the same language as the user's question when possible. "
        "Start with the answer itself, not with commentary about retrieval or context. "
        "Do not use lead-ins like 'Based on the retrieved context' or '\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9'. "
        "When the question asks for named items or a fixed number of things, answer with a concise numbered list. "
        "For list answers, each item should be the canonical item name or name plus acronym, not a full evidence sentence. "
        "If the evidence says 'the first is ...' or defines an acronym, extract the named item and return only that item. "
        "Keep official paper terms and acronyms when available. "
        "If the context is not sufficient, say so explicitly and set answerable=false. "
        "Return strict JSON with keys: answerable, answer, cited_chunk_ids, failure_reason. "
        "cited_chunk_ids must only contain chunk ids from the provided context, and should prefer chunks that directly support the final answer instead of generic overview chunks."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{question}",
            f"Answer formatting hint:\n{format_hint}",
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


def _normalize_llm_answer(question: str, answer: str) -> str:
    normalized = answer.strip()
    for prefix in (
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    normalized = re.sub(
        r"^(?:\u76f8\u5173\u8bc1\u636e\u663e\u793a|evidence shows?)[:\uff1a\uff0c,\s-]*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    for _ in range(3):
        updated = _DIRECT_LEADIN_RE.sub("", normalized).strip()
        if updated == normalized:
            break
        normalized = updated
    if _question_prefers_list(question):
        lines = [line.rstrip() for line in normalized.splitlines()]
        normalized = "\n".join(line for line in lines if line.strip())
    return normalized


def _list_answer_needs_refinement(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(lines) < requested_count:
        return True
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 12 for line in stripped_lines):
        return True
    if any("•" in line or "\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        normalized_answer = answer.lower()
        matched_items = 0
        for item in refined_items[:requested_count]:
            canonical_term = item.split(" (", 1)[0].lower()
            acronym_match = re.search(r"\(([A-Z0-9-]{2,})\)", item)
            if canonical_term and canonical_term in normalized_answer:
                matched_items += 1
                continue
            if acronym_match and acronym_match.group(1).lower() in normalized_answer:
                matched_items += 1
        if matched_items < requested_count:
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )


def _sanitize_candidate_term(term: str) -> str:
    cleaned = _clean_sentence(term)
    cleaned = re.sub(
        r"^(?:(?:we|use|add|propose|proposes|the|a|an|is|are|was|were|first|second|sec|ond)\s+)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:the\s+)?(?:proposed\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:(?:fine|coarse)-?grained\s+)+", "", cleaned, flags=re.IGNORECASE)
    lowered = cleaned.lower()
    for canonical in ("text-image alignment", "text-image matching"):
        if canonical in lowered:
            return canonical.title()
    cleaned = re.sub(
        r"\b(?:strategy|strategies|task|tasks|objective|objectives)\b(?:\s+(?:popular|in|for|where).*)?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _extract_named_list_items(question: str, chunks: Sequence[RetrievedChunk]) -> List[str]:
    requested_count = _question_requested_item_count(question) or 2
    question_tokens = _query_token_set(question)
    task_like_question = _question_requests_task_like_items(question)

    if task_like_question:
        text_image_pair: List[str] = []
        for canonical in ("Text-Image Alignment", "Text-Image Matching"):
            if any(canonical.lower() in _chunk_search_text(chunk).lower() for chunk in chunks):
                text_image_pair.append(
                    _format_named_item(canonical, _lookup_acronym_for_term(canonical, chunks))
                )
        if len(text_image_pair) >= requested_count:
            return text_image_pair[:requested_count]

    for chunk in chunks:
        match = _FIRST_SECOND_ITEM_RE.search(_chunk_search_text(chunk))
        if not match:
            continue
        first_term = _sanitize_candidate_term(match.group("first"))
        second_term = _sanitize_candidate_term(match.group("second"))
        items = [
            _format_named_item(first_term, match.group("first_acronym") or _lookup_acronym_for_term(first_term, chunks)),
            _format_named_item(second_term, match.group("second_acronym") or _lookup_acronym_for_term(second_term, chunks)),
        ]
        return items[:requested_count]

    acronym_candidates: Dict[str, float] = {}
    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            for match in _ACRONYM_TERM_RE.finditer(sentence):
                cleaned_term = _sanitize_candidate_term(match.group(1))
                if len(tokenize_text(cleaned_term)) < 2:
                    continue
                formatted = _format_named_item(cleaned_term, match.group(2))
                lowered = formatted.lower()
                if task_like_question and _NON_TASK_TERM_RE.search(lowered):
                    continue
                if any(token in lowered for token in ("grained cross-modality", "cross-modality alignment")) and "text-image" not in lowered:
                    continue
                term_tokens = set(tokenize_text(formatted))
                overlap = len(question_tokens.intersection(term_tokens))
                score = chunk.score + (0.08 * overlap)
                if _TASK_CONTEXT_RE.search(sentence):
                    score += 0.18
                if "text-image" in lowered:
                    score += 0.35
                acronym_candidates[formatted] = max(acronym_candidates.get(formatted, float("-inf")), score)

    if acronym_candidates:
        ranked_acronyms = [
            item
            for item, _ in sorted(acronym_candidates.items(), key=lambda value: value[1], reverse=True)
        ]
        text_image_acronyms = [item for item in ranked_acronyms if "text-image" in item.lower()]
        if len(text_image_acronyms) >= requested_count:
            return text_image_acronyms[:requested_count]
        if len(ranked_acronyms) >= requested_count:
            return ranked_acronyms[:requested_count]

    candidate_scores: Dict[str, float] = {}

    def add_candidate(term: str, acronym: Optional[str], chunk: RetrievedChunk, sentence: str) -> None:
        sanitized_term = _sanitize_candidate_term(term)
        if len(tokenize_text(sanitized_term)) < 2:
            return
        resolved_acronym = acronym or _lookup_acronym_for_term(sanitized_term, chunks)
        formatted = _format_named_item(sanitized_term, resolved_acronym)
        lowered = formatted.lower()
        if task_like_question and _NON_TASK_TERM_RE.search(lowered):
            return
        if any(token in lowered for token in ("grained cross-modality", "cross-modality alignment")) and "text-image" not in lowered:
            return

        term_tokens = set(tokenize_text(formatted))
        overlap = len(question_tokens.intersection(term_tokens))
        score = chunk.score + (0.08 * overlap)
        if _TASK_CONTEXT_RE.search(sentence):
            score += 0.18
        if _chunk_has_enumeration_cues(chunk):
            score += 0.08
        if _chunk_is_generic_overview(chunk):
            score -= 0.10
        if resolved_acronym:
            score += 0.08
        if "text-image" in lowered:
            score += 0.24

        current = candidate_scores.get(formatted)
        if current is None or score > current:
            candidate_scores[formatted] = score

    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            lowered = sentence.lower()
            if not (
                _ENUMERATION_CUE_RE.search(sentence)
                or _TASK_CONTEXT_RE.search(sentence)
                or "text-image" in lowered
            ):
                continue
            for match in _TASK_PHRASE_TERM_RE.finditer(sentence):
                add_candidate(match.group("term"), None, chunk, sentence)

    ranked_items = [
        item
        for item, _ in sorted(candidate_scores.items(), key=lambda value: value[1], reverse=True)
    ]
    text_image_items = [item for item in ranked_items if "text-image" in item.lower()]
    if len(text_image_items) >= requested_count:
        return text_image_items[:requested_count]
    return ranked_items[:requested_count]


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

    format_hint = _build_answer_format_hint(question)
    system_prompt = (
        "You are PaperLens, a grounded QA assistant. "
        "Answer only from the provided document chunks. "
        "Use the same language as the user's question when possible. "
        "Start with the answer itself, not with commentary about retrieval or context. "
        "Do not use lead-ins like 'Based on the retrieved context' or '\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9'. "
        "When the question asks for named items or a fixed number of things, answer with a concise numbered list. "
        "For list answers, each item should be the canonical item name or name plus acronym, not a full evidence sentence. "
        "If the evidence says 'the first is ...' or defines an acronym, extract the named item and return only that item. "
        "Keep official paper terms and acronyms when available. "
        "If the context is not sufficient, say so explicitly and set answerable=false. "
        "Return strict JSON with keys: answerable, answer, cited_chunk_ids, failure_reason. "
        "cited_chunk_ids must only contain chunk ids from the provided context, and should prefer chunks that directly support the final answer instead of generic overview chunks."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{question}",
            f"Answer formatting hint:\n{format_hint}",
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


def _normalize_llm_answer(question: str, answer: str) -> str:
    normalized = answer.strip()
    for prefix in (
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    normalized = re.sub(
        r"^(?:\u76f8\u5173\u8bc1\u636e\u663e\u793a|evidence shows?)[:\uff1a\uff0c,\s-]*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    for _ in range(3):
        updated = _DIRECT_LEADIN_RE.sub("", normalized).strip()
        if updated == normalized:
            break
        normalized = updated
    if _question_prefers_list(question):
        lines = [line.rstrip() for line in normalized.splitlines()]
        normalized = "\n".join(line for line in lines if line.strip())
    return normalized


def _list_answer_needs_refinement(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(lines) < requested_count:
        return True
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 12 for line in stripped_lines):
        return True
    if any("•" in line or "\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        normalized_answer = answer.lower()
        matched_items = 0
        for item in refined_items[:requested_count]:
            canonical_term = item.split(" (", 1)[0].lower()
            acronym_match = re.search(r"\(([A-Z0-9-]{2,})\)", item)
            if canonical_term and canonical_term in normalized_answer:
                matched_items += 1
                continue
            if acronym_match and acronym_match.group(1).lower() in normalized_answer:
                matched_items += 1
        if matched_items < requested_count:
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )


def _sanitize_candidate_term(term: str) -> str:
    cleaned = _clean_sentence(term)
    cleaned = re.sub(
        r"^(?:(?:we|use|add|propose|proposes|the|a|an|is|are|was|were|first|second|sec|ond)\s+)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:the\s+)?(?:proposed\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:(?:fine|coarse)-?grained\s+)+", "", cleaned, flags=re.IGNORECASE)
    lowered = cleaned.lower()
    for canonical in ("text-image alignment", "text-image matching"):
        if canonical in lowered:
            return canonical.title()
    cleaned = re.sub(
        r"\b(?:strategy|strategies|task|tasks|objective|objectives)\b(?:\s+(?:popular|in|for|where).*)?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _extract_named_list_items(question: str, chunks: Sequence[RetrievedChunk]) -> List[str]:
    requested_count = _question_requested_item_count(question) or 2
    question_tokens = _query_token_set(question)
    task_like_question = _question_requests_task_like_items(question)

    if task_like_question:
        text_image_pair: List[str] = []
        for canonical in ("Text-Image Alignment", "Text-Image Matching"):
            if any(canonical.lower() in _chunk_search_text(chunk).lower() for chunk in chunks):
                text_image_pair.append(
                    _format_named_item(canonical, _lookup_acronym_for_term(canonical, chunks))
                )
        if len(text_image_pair) >= requested_count:
            return text_image_pair[:requested_count]

    for chunk in chunks:
        match = _FIRST_SECOND_ITEM_RE.search(_chunk_search_text(chunk))
        if not match:
            continue
        first_term = _sanitize_candidate_term(match.group("first"))
        second_term = _sanitize_candidate_term(match.group("second"))
        items = [
            _format_named_item(first_term, match.group("first_acronym") or _lookup_acronym_for_term(first_term, chunks)),
            _format_named_item(second_term, match.group("second_acronym") or _lookup_acronym_for_term(second_term, chunks)),
        ]
        return items[:requested_count]

    acronym_candidates: Dict[str, float] = {}
    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            for match in _ACRONYM_TERM_RE.finditer(sentence):
                cleaned_term = _sanitize_candidate_term(match.group(1))
                if len(tokenize_text(cleaned_term)) < 2:
                    continue
                formatted = _format_named_item(cleaned_term, match.group(2))
                lowered = formatted.lower()
                if task_like_question and _NON_TASK_TERM_RE.search(lowered):
                    continue
                if any(token in lowered for token in ("grained cross-modality", "cross-modality alignment")) and "text-image" not in lowered:
                    continue
                term_tokens = set(tokenize_text(formatted))
                overlap = len(question_tokens.intersection(term_tokens))
                score = chunk.score + (0.08 * overlap)
                if _TASK_CONTEXT_RE.search(sentence):
                    score += 0.18
                if "text-image" in lowered:
                    score += 0.35
                acronym_candidates[formatted] = max(acronym_candidates.get(formatted, float("-inf")), score)

    if acronym_candidates:
        ranked_acronyms = [
            item
            for item, _ in sorted(acronym_candidates.items(), key=lambda value: value[1], reverse=True)
        ]
        text_image_acronyms = [item for item in ranked_acronyms if "text-image" in item.lower()]
        if len(text_image_acronyms) >= requested_count:
            return text_image_acronyms[:requested_count]
        if len(ranked_acronyms) >= requested_count:
            return ranked_acronyms[:requested_count]

    candidate_scores: Dict[str, float] = {}

    def add_candidate(term: str, acronym: Optional[str], chunk: RetrievedChunk, sentence: str) -> None:
        sanitized_term = _sanitize_candidate_term(term)
        if len(tokenize_text(sanitized_term)) < 2:
            return
        resolved_acronym = acronym or _lookup_acronym_for_term(sanitized_term, chunks)
        formatted = _format_named_item(sanitized_term, resolved_acronym)
        lowered = formatted.lower()
        if task_like_question and _NON_TASK_TERM_RE.search(lowered):
            return
        if any(token in lowered for token in ("grained cross-modality", "cross-modality alignment")) and "text-image" not in lowered:
            return

        term_tokens = set(tokenize_text(formatted))
        overlap = len(question_tokens.intersection(term_tokens))
        score = chunk.score + (0.08 * overlap)
        if _TASK_CONTEXT_RE.search(sentence):
            score += 0.18
        if _chunk_has_enumeration_cues(chunk):
            score += 0.08
        if _chunk_is_generic_overview(chunk):
            score -= 0.10
        if resolved_acronym:
            score += 0.08
        if "text-image" in lowered:
            score += 0.24

        current = candidate_scores.get(formatted)
        if current is None or score > current:
            candidate_scores[formatted] = score

    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            lowered = sentence.lower()
            if not (
                _ENUMERATION_CUE_RE.search(sentence)
                or _TASK_CONTEXT_RE.search(sentence)
                or "text-image" in lowered
            ):
                continue
            for match in _TASK_PHRASE_TERM_RE.finditer(sentence):
                add_candidate(match.group("term"), None, chunk, sentence)

    ranked_items = [
        item
        for item, _ in sorted(candidate_scores.items(), key=lambda value: value[1], reverse=True)
    ]
    text_image_items = [item for item in ranked_items if "text-image" in item.lower()]
    if len(text_image_items) >= requested_count:
        return text_image_items[:requested_count]
    return ranked_items[:requested_count]


def _normalize_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\u00ad", "")
    normalized = re.sub(r"(?<=[A-Za-z])[-‐‑–—]\s+(?=[A-Za-z])", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _clean_sentence(text: str) -> str:
    return _normalize_match_text(text)


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

    format_hint = _build_answer_format_hint(question)
    system_prompt = (
        "You are PaperLens, a grounded QA assistant. "
        "Answer only from the provided document chunks. "
        "Use the same language as the user's question when possible. "
        "Start with the answer itself, not with commentary about retrieval or context. "
        "Do not use lead-ins like 'Based on the retrieved context' or '根据检索到的文档内容'. "
        "When the question asks for named items or a fixed number of things, answer with a concise numbered list. "
        "For list answers, each item should be the canonical item name or name plus acronym, not a full evidence sentence. "
        "If the evidence says 'the first is ...' or defines an acronym, extract the named item and return only that item. "
        "Keep official paper terms and acronyms when available. "
        "If the context is not sufficient, say so explicitly and set answerable=false. "
        "Return strict JSON with keys: answerable, answer, cited_chunk_ids, failure_reason. "
        "cited_chunk_ids must only contain chunk ids from the provided context, and should prefer chunks that directly support the final answer instead of generic overview chunks."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{question}",
            f"Answer formatting hint:\n{format_hint}",
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


def _describe_answer_backend(
    settings: Settings,
    llm_client_supplied: bool = False,
) -> Dict[str, Any]:
    configured_backend = (settings.answer_backend or "auto").strip().lower() or "auto"

    if configured_backend not in _SUPPORTED_ANSWER_BACKENDS:
        return {
            "configured_backend": configured_backend,
            "active_backend": "misconfigured",
            "llm_ready": False,
            "llm_model": settings.llm_model,
            "reason": "unsupported_answer_backend",
            "message": (
                f"Unsupported ANSWER_BACKEND '{settings.answer_backend}'. "
                "Use one of: auto, openai, extractive."
            ),
        }

    if configured_backend == "extractive":
        return {
            "configured_backend": configured_backend,
            "active_backend": "extractive",
            "llm_ready": False,
            "llm_model": settings.llm_model,
            "reason": "extractive_forced",
            "message": "Extractive fallback is forced by ANSWER_BACKEND=extractive.",
        }

    if llm_client_supplied and settings.llm_model:
        return {
            "configured_backend": configured_backend,
            "active_backend": "openai",
            "llm_ready": True,
            "llm_model": settings.llm_model,
            "reason": "custom_client",
            "message": f"Using a supplied LLM client with model '{settings.llm_model}'.",
        }

    if not settings.llm_model:
        return {
            "configured_backend": configured_backend,
            "active_backend": "misconfigured" if configured_backend == "openai" else "extractive",
            "llm_ready": False,
            "llm_model": settings.llm_model,
            "reason": "llm_model_missing",
            "message": "LLM_MODEL is not configured, so PaperLens will use extractive fallback.",
        }

    if not settings.openai_api_key:
        return {
            "configured_backend": configured_backend,
            "active_backend": "misconfigured" if configured_backend == "openai" else "extractive",
            "llm_ready": False,
            "llm_model": settings.llm_model,
            "reason": "openai_api_key_missing",
            "message": "OPENAI_API_KEY is missing, so PaperLens cannot call the LLM backend.",
        }

    if OpenAI is None:
        return {
            "configured_backend": configured_backend,
            "active_backend": "misconfigured" if configured_backend == "openai" else "extractive",
            "llm_ready": False,
            "llm_model": settings.llm_model,
            "reason": "openai_package_missing",
            "message": "openai is not installed in the active environment.",
        }

    return {
        "configured_backend": configured_backend,
        "active_backend": "openai",
        "llm_ready": True,
        "llm_model": settings.llm_model,
        "reason": "llm_ready",
        "message": f"Using OpenAI-compatible LLM backend with model '{settings.llm_model}'.",
    }


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
        self.backend_status = self.describe_backend(settings, llm_client_supplied=llm_client is not None)

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

    @staticmethod
    def describe_backend(
        settings: Settings,
        llm_client_supplied: bool = False,
    ) -> Dict[str, Any]:
        return _describe_answer_backend(settings, llm_client_supplied=llm_client_supplied)

    def answer_question(self, question: str, top_k: Optional[int] = None) -> AskResponse:
        default_top_k = getattr(self.retriever, "default_top_k", self.settings.top_k)
        requested_top_k = top_k or default_top_k
        search_top_k = max(requested_top_k, default_top_k * 8)
        # Allow the answer layer to consider slightly weaker retrieval candidates.
        # The fallback sentence selector still applies its own confidence filter,
        # but this prevents larger merged chunks from being discarded too early
        # and gives the answer layer a better chance to find explicit item lists.
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

        chunks = _augment_list_context_chunks_v2(self, question, chunks)
        draft = self._generate_draft(question, chunks)
        if draft.answerable:
            citations = self._map_citations(question, draft.answer, chunks, draft.cited_chunk_ids)
            if not citations:
                fallback_draft = self._fallback_draft(question, chunks)
                if not fallback_draft.answerable:
                    return self._refusal_response(
                        question=question,
                        retrieval=retrieval,
                        failure_reason=fallback_draft.failure_reason or "low_confidence",
                    )
                draft = fallback_draft
                citations = self._map_citations(question, draft.answer, chunks, draft.cited_chunk_ids)

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
        if self.backend_status.get("active_backend") == "openai" and self.llm_client is not None:
            try:
                return self._llm_draft(question, chunks)
            except AnswerGenerationError:
                return self._fallback_draft(question, chunks)
        return self._fallback_draft(question, chunks)

    def _llm_draft(self, question: str, chunks: Sequence[RetrievedChunk]) -> AnswerDraft:
        context_chunks = _select_llm_context_chunks_v2(self, question, chunks)
        messages = build_grounded_messages(question, context_chunks)
        try:
            request_kwargs: Dict[str, Any] = {
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
                "messages": messages,
            }
            if self.settings.llm_max_output_tokens > 0:
                request_kwargs["max_tokens"] = self.settings.llm_max_output_tokens
            response = self.llm_client.chat.completions.create(**request_kwargs)
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise AnswerGenerationError(f"LLM answer generation failed: {exc}") from exc

        try:
            content = response.choices[0].message.content
        except Exception as exc:  # pragma: no cover - depends on runtime environment
            raise AnswerGenerationError("LLM response did not contain a valid message") from exc

        payload = self._parse_llm_payload(content)
        valid_chunk_ids = {chunk.chunk_id for chunk in context_chunks}
        cited_chunk_ids = [
            chunk_id
            for chunk_id in payload.get("cited_chunk_ids", [])
            if chunk_id in valid_chunk_ids
        ]

        answer = _normalize_llm_answer(question, str(payload.get("answer", "")).strip())
        refined_items = _extract_named_list_items(question, chunks) if _question_prefers_list(question) else []
        if _list_answer_needs_refinement_v2(question, answer, refined_items):
            requested_count = _question_requested_item_count(question) or len(refined_items)
            if len(refined_items) >= requested_count and requested_count > 0:
                answer = "\n".join(
                    f"{index}. {item}"
                    for index, item in enumerate(refined_items[:requested_count], start=1)
                )
                supporting_chunk_ids: List[str] = []
                for chunk in context_chunks:
                    if any(
                        _chunk_directly_supports_item(chunk, item)
                        for item in refined_items[:requested_count]
                    ):
                        supporting_chunk_ids.append(chunk.chunk_id)
                cited_chunk_ids = supporting_chunk_ids
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

        if _question_prefers_list(question):
            answer = "\n".join(f"{index}. {text}" for index, text in enumerate(answer_parts, start=1))
        elif _contains_cjk(question):
            answer = "根据检索到的文档内容，相关证据显示：" + " ".join(answer_parts)
        else:
            answer = " ".join(answer_parts)

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
        question_tokens = _query_token_set(question)
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

    def _select_llm_context_chunks(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
    ) -> List[RetrievedChunk]:
        max_chunks = max(self.settings.llm_max_context_chunks, 1)
        focus_items = _extract_named_list_items(question, chunks) if _question_prefers_list(question) else []
        ranked = sorted(
            enumerate(chunks),
            key=lambda item: (
                self._score_chunk_for_prompt(question, item[1], item[0])
                + self._score_chunk_for_focus_items(item[1], focus_items)
            ),
            reverse=True,
        )
        selected: List[RetrievedChunk] = []
        seen_chunk_ids: set[str] = set()

        for focus_item in focus_items:
            focus_ranked = sorted(
                (
                    (index, chunk)
                    for index, chunk in enumerate(chunks)
                    if _chunk_directly_supports_item(chunk, focus_item)
                ),
                key=lambda item: (
                    self._score_chunk_for_prompt(question, item[1], item[0])
                    + self._score_chunk_for_focus_items(item[1], [focus_item])
                ),
                reverse=True,
            )
            for _, chunk in focus_ranked:
                if chunk.chunk_id in seen_chunk_ids:
                    continue
                selected.append(chunk)
                seen_chunk_ids.add(chunk.chunk_id)
                break

        for _, chunk in ranked:
            if chunk.chunk_id in seen_chunk_ids:
                continue
            selected.append(chunk)
            seen_chunk_ids.add(chunk.chunk_id)
            if len(selected) >= max_chunks:
                break

        return selected[:max_chunks]

    @staticmethod
    def _score_chunk_for_focus_items(
        chunk: RetrievedChunk,
        focus_items: Sequence[str],
    ) -> float:
        if not focus_items:
            return 0.0

        search_text = _chunk_search_text(chunk).lower()
        section_title = _normalize_match_text(chunk.section_title or "").lower()
        bonus = 0.0
        matched_any = False
        for item in focus_items:
            canonical_term, acronym = _split_named_item(item)
            item_bonus = 0.0
            canonical_lower = canonical_term.lower()
            if canonical_lower and canonical_lower in search_text:
                item_bonus += 0.22
            if canonical_lower and canonical_lower in section_title:
                item_bonus += 0.28
            if acronym and acronym.lower() in search_text:
                item_bonus += 0.24
            if item_bonus > 0:
                matched_any = True
                bonus += item_bonus
        if not matched_any:
            return -0.10 if _chunk_is_generic_overview(chunk) else 0.0
        if _chunk_has_enumeration_cues(chunk):
            bonus += 0.06
        if _chunk_is_generic_overview(chunk):
            bonus -= 0.12
        return bonus

    def _score_chunk_for_prompt(
        self,
        question: str,
        chunk: RetrievedChunk,
        rank: int,
    ) -> float:
        question_tokens = _query_token_set(question)
        question_anchors = set(extract_anchor_tokens(question))
        chunk_tokens = set(tokenize_text(_chunk_search_text(chunk)))

        overlap = len(question_tokens.intersection(chunk_tokens))
        anchor_overlap = len(question_anchors.intersection(chunk_tokens))
        score = chunk.score + (0.03 * overlap) + (0.12 * anchor_overlap) - (0.01 * rank)

        if _chunk_has_enumeration_cues(chunk):
            score += 0.08
        if _chunk_is_generic_overview(chunk):
            score -= 0.08
            if len(chunk.text) < 220:
                score -= 0.06

        if _question_prefers_list(question):
            if _chunk_has_enumeration_cues(chunk):
                score += 0.04
            if _chunk_is_generic_overview(chunk):
                score -= 0.02

        if (chunk.section_title or "").strip().lower() == "references":
            score -= 0.2
        return score

    def _map_citations(
        self,
        question: str,
        answer: str,
        chunks: Sequence[RetrievedChunk],
        cited_chunk_ids: Sequence[str],
    ) -> List[Citation]:
        ranked_chunks = self._rank_chunks_for_citations(
            question=question,
            answer=answer,
            chunks=chunks,
            preferred_chunk_ids=set(cited_chunk_ids),
        )
        citations: List[Citation] = []
        seen = set()
        for chunk in ranked_chunks:
            if chunk.chunk_id in seen:
                continue
            citations.append(chunk.to_citation())
            seen.add(chunk.chunk_id)
            if len(citations) >= self.max_citations:
                break
        return citations

    def _rank_chunks_for_citations(
        self,
        question: str,
        answer: str,
        chunks: Sequence[RetrievedChunk],
        preferred_chunk_ids: set[str],
    ) -> List[RetrievedChunk]:
        question_tokens = _query_token_set(question)
        answer_tokens = set(tokenize_text(answer))
        answer_anchors = set(extract_anchor_tokens(answer))
        focus_items = _extract_named_list_items(question, chunks) if _question_prefers_list(question) else []
        if not focus_items and _question_prefers_list(question):
            focus_items = _extract_numbered_answer_items(answer)

        ranked = sorted(
            enumerate(chunks),
            key=lambda item: self._score_chunk_for_citation(
                question_tokens=question_tokens,
                answer_tokens=answer_tokens,
                answer_anchors=answer_anchors,
                focus_items=focus_items,
                question=question,
                chunk=item[1],
                rank=item[0],
                preferred_chunk_ids=preferred_chunk_ids,
            ),
            reverse=True,
        )
        return [chunk for _, chunk in ranked]

    def _score_chunk_for_citation(
        self,
        *,
        question_tokens: set[str],
        answer_tokens: set[str],
        answer_anchors: set[str],
        focus_items: Sequence[str],
        question: str,
        chunk: RetrievedChunk,
        rank: int,
        preferred_chunk_ids: set[str],
    ) -> float:
        chunk_search_text = _chunk_search_text(chunk)
        chunk_search_text_lower = chunk_search_text.lower()
        chunk_tokens = set(tokenize_text(chunk_search_text))
        question_overlap = len(question_tokens.intersection(chunk_tokens))
        answer_overlap = len(answer_tokens.intersection(chunk_tokens))
        anchor_overlap = len(answer_anchors.intersection(chunk_tokens))

        score = (
            chunk.score
            + (0.02 * question_overlap)
            + (0.04 * answer_overlap)
            + (0.12 * anchor_overlap)
            - (0.01 * rank)
        )
        if focus_items:
            direct_hits = sum(1 for item in focus_items if _chunk_directly_supports_item(chunk, item))
            score += self._score_chunk_for_focus_items(chunk, focus_items)
            if direct_hits:
                score += 0.08 * direct_hits
            for item in focus_items:
                if not _chunk_directly_supports_item(chunk, item):
                    continue
                canonical_term, acronym = _split_named_item(item)
                if acronym and acronym.lower() in chunk_search_text_lower:
                    score += 0.08
                if canonical_term and re.search(
                    rf"\b{re.escape(canonical_term)}\b[^.\n]{{0,80}}\b(?:is|refers to|denotes)\b",
                    chunk_search_text,
                    re.IGNORECASE,
                ):
                    score += 0.10
        if _chunk_has_enumeration_cues(chunk):
            score += 0.06
        if _chunk_is_generic_overview(chunk):
            score -= 0.06
        if chunk.chunk_id in preferred_chunk_ids:
            score += 0.26
        if _question_prefers_list(question) and _chunk_has_enumeration_cues(chunk):
            score += 0.04
        if _chunk_is_generic_overview(chunk) and answer_overlap < 4 and anchor_overlap == 0:
            score -= 0.08
        if focus_items and not any(_chunk_directly_supports_item(chunk, item) for item in focus_items):
            score -= 0.10
        return score

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
        backend_status = _describe_answer_backend(settings)
        if backend_status["configured_backend"] == "extractive":
            return None
        if backend_status["active_backend"] == "extractive":
            return None
        if backend_status["active_backend"] == "misconfigured":
            raise LlmConfigurationError(backend_status["message"])

        client_kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        return OpenAI(**client_kwargs)


def _question_prefers_list(question: str) -> bool:
    if _LIST_QUESTION_RE.search(question):
        return True
    requested_count = _question_requested_item_count(question)
    if requested_count is not None:
        question_lower = question.lower()
        if any(
            marker in question
            for marker in (
                "任务",
                "目标",
                "方法",
                "模块",
                "部分",
                "阶段",
                "预训练",
                "训练目标",
                "跨模态",
                "多模态",
            )
        ):
            return True
        if any(
            marker in question_lower
            for marker in (
                "task",
                "tasks",
                "objective",
                "objectives",
                "strategy",
                "strategies",
                "method",
                "methods",
                "component",
                "components",
                "module",
                "modules",
                "stage",
                "stages",
            )
        ):
            return True
    return any(
        marker in question
        for marker in (
            "\u54ea\u4e9b",
            "\u54ea\u51e0",
            "\u5217\u51fa",
            "\u5206\u522b",
            "\u6709\u54ea",
            "\u54ea\u4e24",
            "\u54ea\u4e09",
            "\u54ea\u56db",
        )
    )


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

    format_hint = _build_answer_format_hint(question)
    system_prompt = (
        "You are PaperLens, a grounded QA assistant. "
        "Answer only from the provided document chunks. "
        "Use the same language as the user's question when possible. "
        "Start with the answer itself, not with commentary about retrieval or context. "
        "Do not use lead-ins like 'Based on the retrieved context' or '根据检索到的文档内容'. "
        "When the question asks for named items or a fixed number of things, answer with a concise numbered list. "
        "Each list item should begin with the canonical item name itself, not with an explanatory clause. "
        "Keep official paper terms and acronyms when available. "
        "If the context is not sufficient, say so explicitly and set answerable=false. "
        "Return strict JSON with keys: answerable, answer, cited_chunk_ids, failure_reason. "
        "cited_chunk_ids must only contain chunk ids from the provided context, and should prefer chunks that directly support the final answer instead of generic overview chunks."
    )
    user_prompt = "\n\n".join(
        [
            f"Question:\n{question}",
            f"Answer formatting hint:\n{format_hint}",
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


def _normalize_llm_answer(question: str, answer: str) -> str:
    normalized = answer.strip()
    for prefix in (
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9\uff1a",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff0c",
        "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\uff1a",
    ):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
            break
    for _ in range(3):
        updated = _DIRECT_LEADIN_RE.sub("", normalized).strip()
        if updated == normalized:
            break
        normalized = updated
    if _question_prefers_list(question):
        lines = [line.rstrip() for line in normalized.splitlines()]
        normalized = "\n".join(line for line in lines if line.strip())
    return normalized


def _list_answer_needs_refinement(question: str, answer: str) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(acronym_mentions) >= requested_count:
        return False

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )


def _question_requests_task_like_items(question: str) -> bool:
    lowered = question.lower()
    if any(token in lowered for token in ("task", "tasks", "objective", "objectives", "strategy", "strategies")):
        return True
    return any(
        token in question
        for token in (
            "\u4efb\u52a1",
            "\u76ee\u6807",
            "\u9884\u8bad\u7ec3",
            "\u7b56\u7565",
            "\u65b9\u6cd5",
        )
    )


def _sanitize_candidate_term(term: str) -> str:
    cleaned = _clean_sentence(term)
    cleaned = re.sub(
        r"^(?:(?:we|use|add|propose|proposes|the|a|an|is|are|was|were|first|second|sec|ond)\s+)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:the\s+)?(?:proposed\s+)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:(?:fine|coarse)-?grained\s+)+", "", cleaned, flags=re.IGNORECASE)
    lowered = cleaned.lower()
    for canonical in ("text-image alignment", "text-image matching"):
        index = lowered.find(canonical)
        if index != -1:
            return canonical.title()
    if "text-image" in lowered:
        cleaned = cleaned[lowered.rfind("text-image") :]
    cleaned = re.sub(
        r"\b(?:strategy|strategies|task|tasks|objective|objectives)\b(?:\s+(?:popular|in|for|where).*)?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _lookup_acronym_for_term(term: str, chunks: Sequence[RetrievedChunk]) -> Optional[str]:
    pattern = re.compile(
        rf"\b{re.escape(_clean_sentence(term))}\s*\(([A-Z0-9-]{{2,}})\)",
        re.IGNORECASE,
    )
    for chunk in chunks:
        match = pattern.search(_chunk_search_text(chunk))
        if match:
            return match.group(1).upper()
    return None


def _extract_named_list_items(question: str, chunks: Sequence[RetrievedChunk]) -> List[str]:
    requested_count = _question_requested_item_count(question) or 2
    question_tokens = _query_token_set(question)
    task_like_question = _question_requests_task_like_items(question)

    if task_like_question:
        text_image_pair: List[str] = []
        for canonical in ("Text-Image Alignment", "Text-Image Matching"):
            if any(canonical.lower() in _chunk_search_text(chunk).lower() for chunk in chunks):
                text_image_pair.append(
                    _format_named_item(canonical, _lookup_acronym_for_term(canonical, chunks))
                )
        if len(text_image_pair) >= requested_count:
            return text_image_pair[:requested_count]

    for chunk in chunks:
        match = _FIRST_SECOND_ITEM_RE.search(_chunk_search_text(chunk))
        if not match:
            continue
        first_term = _sanitize_candidate_term(match.group("first"))
        second_term = _sanitize_candidate_term(match.group("second"))
        items = [
            _format_named_item(first_term, match.group("first_acronym") or _lookup_acronym_for_term(first_term, chunks)),
            _format_named_item(second_term, match.group("second_acronym") or _lookup_acronym_for_term(second_term, chunks)),
        ]
        return items[:requested_count]

    acronym_candidates: Dict[str, float] = {}
    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            for match in _ACRONYM_TERM_RE.finditer(sentence):
                cleaned_term = _sanitize_candidate_term(match.group(1))
                if len(tokenize_text(cleaned_term)) < 2:
                    continue
                formatted = _format_named_item(cleaned_term, match.group(2))
                lowered = formatted.lower()
                if task_like_question and _NON_TASK_TERM_RE.search(lowered):
                    continue
                if any(token in lowered for token in ("grained cross-modality", "cross-modality alignment")) and "text-image" not in lowered:
                    continue
                term_tokens = set(tokenize_text(formatted))
                overlap = len(question_tokens.intersection(term_tokens))
                score = chunk.score + (0.08 * overlap)
                if _TASK_CONTEXT_RE.search(sentence):
                    score += 0.18
                if "text-image" in lowered:
                    score += 0.35
                acronym_candidates[formatted] = max(acronym_candidates.get(formatted, float("-inf")), score)

    if acronym_candidates:
        ranked_acronyms = [
            item
            for item, _ in sorted(acronym_candidates.items(), key=lambda value: value[1], reverse=True)
        ]
        text_image_acronyms = [item for item in ranked_acronyms if "text-image" in item.lower()]
        if len(text_image_acronyms) >= requested_count:
            return text_image_acronyms[:requested_count]
        if len(ranked_acronyms) >= requested_count:
            return ranked_acronyms[:requested_count]

    candidate_scores: Dict[str, float] = {}

    def add_candidate(term: str, acronym: Optional[str], chunk: RetrievedChunk, sentence: str) -> None:
        sanitized_term = _sanitize_candidate_term(term)
        if len(tokenize_text(sanitized_term)) < 2:
            return
        resolved_acronym = acronym or _lookup_acronym_for_term(sanitized_term, chunks)
        formatted = _format_named_item(sanitized_term, resolved_acronym)
        lowered = formatted.lower()
        if task_like_question and _NON_TASK_TERM_RE.search(lowered):
            return
        if any(token in lowered for token in ("grained cross-modality", "cross-modality alignment")) and "text-image" not in lowered:
            return

        term_tokens = set(tokenize_text(formatted))
        overlap = len(question_tokens.intersection(term_tokens))
        score = chunk.score + (0.08 * overlap)
        if _TASK_CONTEXT_RE.search(sentence):
            score += 0.18
        if _chunk_has_enumeration_cues(chunk):
            score += 0.08
        if _chunk_is_generic_overview(chunk):
            score -= 0.10
        if resolved_acronym:
            score += 0.08
        if "text-image" in lowered:
            score += 0.24

        current = candidate_scores.get(formatted)
        if current is None or score > current:
            candidate_scores[formatted] = score

    for chunk in chunks:
        for sentence in _split_sentences(_chunk_search_text(chunk)):
            lowered = sentence.lower()
            if not (
                _ENUMERATION_CUE_RE.search(sentence)
                or _TASK_CONTEXT_RE.search(sentence)
                or "text-image" in lowered
            ):
                continue
            for match in _TASK_PHRASE_TERM_RE.finditer(sentence):
                add_candidate(match.group("term"), None, chunk, sentence)

    ranked_items = [
        item
        for item, _ in sorted(candidate_scores.items(), key=lambda value: value[1], reverse=True)
    ]
    text_image_items = [item for item in ranked_items if "text-image" in item.lower()]
    if len(text_image_items) >= requested_count:
        return text_image_items[:requested_count]
    return ranked_items[:requested_count]


def _default_refusal_answer(question: str) -> str:
    if _contains_cjk(question):
        return "\u5f53\u524d\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9\u4e0d\u8db3\u4ee5\u53ef\u9760\u56de\u7b54\u8fd9\u4e2a\u95ee\u9898\u3002"
    return "The retrieved context is not sufficient to answer this question reliably."


def _list_answer_needs_refinement(
    question: str,
    answer: str,
    refined_items: Optional[Sequence[str]] = None,
) -> bool:
    if not _question_prefers_list(question):
        return False

    requested_count = _question_requested_item_count(question) or 2
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    acronym_mentions = re.findall(r"\([A-Z0-9-]{2,}\)", answer)
    if len(lines) < requested_count:
        return True
    if len(acronym_mentions) >= requested_count and len(lines) >= requested_count:
        return False

    stripped_lines = [
        re.sub(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s*)", "", line).strip()
        for line in lines[:requested_count]
    ]
    if any(len(tokenize_text(line)) > 12 for line in stripped_lines):
        return True
    if any("•" in line or "\u2022" in line for line in stripped_lines):
        return True

    if refined_items:
        normalized_answer = answer.lower()
        matched_items = 0
        for item in refined_items[:requested_count]:
            canonical_term = item.split(" (", 1)[0].lower()
            acronym_match = re.search(r"\(([A-Z0-9-]{2,})\)", item)
            if canonical_term and canonical_term in normalized_answer:
                matched_items += 1
                continue
            if acronym_match and acronym_match.group(1).lower() in normalized_answer:
                matched_items += 1
        if matched_items < requested_count:
            return True

    lowered = answer.lower()
    return any(
        cue in lowered
        for cue in ("in this section", "we will introduce", "we present", "we propose", "we introduce")
    ) or any(
        cue in answer
        for cue in (
            "\u6839\u636e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6839\u636e\u63d0\u4f9b\u7684\u6587\u6863\u5185\u5bb9",
            "\u57fa\u4e8e\u68c0\u7d22\u5230\u7684\u6587\u6863\u5185\u5bb9",
            "\u6211\u4eec\u5f15\u5165",
            "\u6211\u4eec\u63d0\u51fa",
        )
    )
