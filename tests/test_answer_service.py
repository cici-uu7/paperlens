from pathlib import Path
from types import SimpleNamespace

from app.core.config import get_settings
from app.models.schemas import RetrievalMetadata
from app.rag import AnswerService, build_grounded_messages
from app.rag.errors import LlmConfigurationError
from app.rag.retriever import RetrievedChunk


class DummyRetriever:
    def __init__(self, chunks, metadata=None):
        self.chunks = chunks
        self.metadata = metadata or RetrievalMetadata(top_k=5, hit_count=len(chunks), latency_ms=3.5)
        self.last_score_threshold = None

    def retrieve(self, query: str, top_k=None, score_threshold=None):
        self.last_score_threshold = score_threshold
        return self.chunks, self.metadata


class QueryAwareDummyRetriever:
    def __init__(self, default_chunks, routes, metadata=None):
        self.default_chunks = default_chunks
        self.routes = routes
        self.metadata = metadata or RetrievalMetadata(top_k=5, hit_count=len(default_chunks), latency_ms=3.5)
        self.calls = []

    def retrieve(self, query: str, top_k=None, score_threshold=None):
        self.calls.append(query)
        for needle, chunks in self.routes:
            if needle in query:
                return chunks, self.metadata
        return self.default_chunks, self.metadata


class DummyLlmClient:
    def __init__(self, content: str):
        self.calls = []

        def _create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=_create
            )
        )


class RawStringLlmClient:
    def __init__(self, content: str):
        self.calls = []

        def _create(**kwargs):
            self.calls.append(kwargs)
            return content

        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=_create
            )
        )


def _build_settings(tmp_path, extra_lines=None):
    env_path = tmp_path / ".env"
    lines = list(extra_lines or [])
    env_path.write_text("\n".join(lines), encoding="utf-8")
    return get_settings(project_root=tmp_path, env_path=env_path)


def test_answer_service_returns_refusal_when_retrieval_is_empty(tmp_path):
    settings = _build_settings(tmp_path)
    retriever = DummyRetriever([])
    service = AnswerService(retriever=retriever, settings=settings)

    response = service.answer_question("What is the GitHub star count in 2026?")

    assert response.answerable is False
    assert response.failure_reason == "insufficient_context"
    assert response.citations == []


def test_answer_service_fallback_returns_grounded_answer_and_citations(tmp_path):
    settings = _build_settings(tmp_path)
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="layoutlm_c0001",
                doc_id="layoutlm",
                doc_name="layoutlm_1912.13318.pdf",
                page_start=1,
                page_end=1,
                section_title="Abstract",
                element_types=["paragraph"],
                score=0.42,
                text="LayoutLM jointly models text and layout information for document understanding.",
            )
        ]
    )
    service = AnswerService(retriever=retriever, settings=settings)

    response = service.answer_question("What does LayoutLM model?")

    assert response.answerable is True
    assert "LayoutLM jointly models text and layout information" in response.answer
    assert response.citations[0].chunk_id == "layoutlm_c0001"
    assert response.citations[0].doc_name == "layoutlm_1912.13318.pdf"


def test_answer_service_refuses_low_confidence_fallback(tmp_path):
    settings = _build_settings(tmp_path)
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="other_c0001",
                doc_id="other",
                doc_name="other.pdf",
                page_start=2,
                page_end=2,
                section_title="Background",
                element_types=["paragraph"],
                score=0.12,
                text="This paragraph discusses a benchmark setup and training schedule.",
            )
        ]
    )
    service = AnswerService(retriever=retriever, settings=settings)

    response = service.answer_question("这些论文在2026年4月的GitHub star分别是多少？")

    assert response.answerable is False
    assert response.failure_reason == "low_confidence"
    assert response.citations == []


def test_answer_service_uses_llm_json_when_available(tmp_path):
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=1",
            "LLM_MAX_OUTPUT_TOKENS=256",
            "LLM_TEMPERATURE=0.1",
        ],
    )
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="layoutlm_c0001",
                doc_id="layoutlm",
                doc_name="layoutlm_1912.13318.pdf",
                page_start=1,
                page_end=1,
                section_title="Abstract",
                element_types=["paragraph"],
                score=0.52,
                text="LayoutLM jointly models text and layout information for document understanding.",
            )
        ]
    )
    llm_client = DummyLlmClient(
        '{"answerable": true, "answer": "LayoutLM jointly models text and layout.", '
        '"cited_chunk_ids": ["layoutlm_c0001"], "failure_reason": null}'
    )
    service = AnswerService(retriever=retriever, settings=settings, llm_client=llm_client)

    response = service.answer_question("What does LayoutLM model?")

    assert response.answerable is True
    assert response.answer == "LayoutLM jointly models text and layout."
    assert response.citations[0].chunk_id == "layoutlm_c0001"
    assert llm_client.calls[0]["model"] == "gpt-test"
    assert llm_client.calls[0]["temperature"] == 0.1
    assert llm_client.calls[0]["max_tokens"] == 256
    assert len(llm_client.calls[0]["messages"]) == 2


def test_answer_service_localizes_chinese_answer_and_enriches_citations(tmp_path):
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=1",
        ],
    )
    runtime_manifest = tmp_path / "reports" / "doc_manifest_runtime.csv"
    runtime_manifest.parent.mkdir(parents=True, exist_ok=True)
    runtime_manifest.write_text(
        "\n".join(
            [
                "filename,title",
                "rag_2005.11401.pdf,Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            ]
        ),
        encoding="utf-8",
    )
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="rag_c0001",
                doc_id="rag",
                doc_name="rag_2005.11401.pdf",
                page_start=6,
                page_end=6,
                section_title="Introduction",
                element_types=["paragraph"],
                score=0.61,
                text=(
                    "RAG combines parametric memory in the generator with non-parametric memory "
                    "stored in a retrievable document index."
                ),
            )
        ]
    )
    llm_client = DummyLlmClient(
        '{"answerable": true, "answer": "RAG combines parametric memory and non-parametric memory.", '
        '"cited_chunk_ids": ["rag_c0001"], "failure_reason": null}'
    )
    translations = {
        "RAG combines parametric memory and non-parametric memory.": "RAG 结合了参数记忆和非参数记忆。",
        (
            "RAG combines parametric memory in the generator with non-parametric memory "
            "stored in a retrievable document index."
        ): "RAG 将生成器中的参数记忆与可检索文档索引中的非参数记忆结合在一起。",
    }

    service = AnswerService(
        retriever=retriever,
        settings=settings,
        llm_client=llm_client,
        text_translator=lambda text, _: translations[text],
    )

    response = service.answer_question("RAG把哪两类记忆结合在一起？")

    assert response.answer == "RAG 结合了参数记忆和非参数记忆。"
    assert response.citations[0].source_title.startswith("Retrieval-Augmented Generation")
    assert response.citations[0].quote_language == "en"
    assert response.citations[0].quote_original.startswith("RAG combines parametric memory")
    assert response.citations[0].quote_translation.startswith("RAG 将生成器中的参数记忆")


def test_answer_service_accepts_raw_string_llm_payload(tmp_path):
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=1",
        ],
    )
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="layoutlm_c0001",
                doc_id="layoutlm",
                doc_name="layoutlm_1912.13318.pdf",
                page_start=1,
                page_end=1,
                section_title="Abstract",
                element_types=["paragraph"],
                score=0.52,
                text="LayoutLM jointly models text and layout information for document understanding.",
            )
        ]
    )
    llm_client = RawStringLlmClient(
        '{"answerable": true, "answer": "LayoutLM jointly models text and layout.", '
        '"cited_chunk_ids": ["layoutlm_c0001"], "failure_reason": null}'
    )
    service = AnswerService(retriever=retriever, settings=settings, llm_client=llm_client)

    response = service.answer_question("What does LayoutLM model?")

    assert response.answerable is True
    assert response.answer == "LayoutLM jointly models text and layout."
    assert response.citations[0].chunk_id == "layoutlm_c0001"


def test_answer_service_uses_fallback_when_llm_refuses_answerable_question(tmp_path):
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=1",
        ],
    )
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="rag_c0001",
                doc_id="rag",
                doc_name="rag_2005.11401.pdf",
                page_start=1,
                page_end=1,
                section_title="Introduction",
                element_types=["paragraph"],
                score=0.46,
                text=(
                    "RAG combines parametric memory in the generator with non-parametric memory "
                    "stored in a retrievable document index."
                ),
            )
        ]
    )
    llm_client = DummyLlmClient(
        '{"answerable": false, "answer": "", "cited_chunk_ids": [], '
        '"failure_reason": "insufficient_context"}'
    )
    service = AnswerService(retriever=retriever, settings=settings, llm_client=llm_client)

    response = service.answer_question("What two kinds of memory does RAG combine?")

    assert response.answerable is True
    assert "parametric memory" in response.answer
    assert response.citations[0].chunk_id == "rag_c0001"


def test_build_grounded_messages_adds_direct_list_hint_for_enumeration_question():
    chunks = [
        RetrievedChunk(
            chunk_id="layoutlmv2_c0007",
            doc_id="layoutlmv2",
            doc_name="layoutlmv2_2012.14740.pdf",
            page_start=2,
            page_end=2,
            section_title="Introduction",
            element_types=["paragraph"],
            score=0.42,
            text=(
                "The first is the text-image alignment strategy Text-Image Alignment (TIA). "
                "The second is the text-image matching strategy Text-Image Matching (TIM)."
            ),
        )
    ]

    messages = build_grounded_messages("LayoutLMv2新增的两个跨模态预训练任务是什么？", chunks)

    assert "Start with the answer itself" in messages[0]["content"]
    assert "numbered list" in messages[0]["content"]
    assert "exactly 2 items" in messages[1]["content"]


def test_build_grounded_messages_adds_direct_list_hint_for_utf8_chinese_enumeration_question():
    question = "LayoutLMv2\u65b0\u589e\u7684\u4e24\u4e2a\u8de8\u6a21\u6001\u9884\u8bad\u7ec3\u4efb\u52a1\u662f\u4ec0\u4e48\uff1f"
    chunks = [
        RetrievedChunk(
            chunk_id="layoutlmv2_c0007",
            doc_id="layoutlmv2",
            doc_name="layoutlmv2_2012.14740.pdf",
            page_start=2,
            page_end=2,
            section_title="Introduction",
            element_types=["paragraph"],
            score=0.42,
            text=(
                "The first is the text-image alignment strategy Text-Image Alignment (TIA). "
                "The second is the text-image matching strategy Text-Image Matching (TIM)."
            ),
        )
    ]

    messages = build_grounded_messages(question, chunks)

    assert "Start with the answer itself" in messages[0]["content"]
    assert "numbered list" in messages[0]["content"]
    assert "exactly 2 items" in messages[1]["content"]


def test_answer_service_augments_utf8_chinese_list_questions_with_item_focused_chunks(tmp_path):
    question = "LayoutLMv2\u65b0\u589e\u7684\u4e24\u4e2a\u8de8\u6a21\u6001\u9884\u8bad\u7ec3\u4efb\u52a1\u662f\u4ec0\u4e48\uff1f"
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=2",
        ],
    )
    default_chunks = [
        RetrievedChunk(
            chunk_id="layoutlmv2_generic",
            doc_id="layoutlmv2",
            doc_name="layoutlmv2_2012.14740.pdf",
            page_start=1,
            page_end=1,
            section_title="Abstract",
            element_types=["paragraph"],
            score=0.61,
            text=(
                "LayoutLMv2 introduces new pre-training tasks for visually-rich document understanding, "
                "including Text-Image Alignment and Text-Image Matching."
            ),
        ),
    ]
    retriever = QueryAwareDummyRetriever(
        default_chunks=default_chunks,
        routes=[
            (
                "Text-Image Alignment",
                [
                    RetrievedChunk(
                        chunk_id="layoutlmv2_tia_focus",
                        doc_id="layoutlmv2",
                        doc_name="layoutlmv2_2012.14740.pdf",
                        page_start=2,
                        page_end=2,
                        section_title="1 Introduction",
                        element_types=["paragraph"],
                        score=0.48,
                        text=(
                            "The first is Text-Image Alignment (TIA), a fine-grained cross-modality alignment task."
                        ),
                    )
                ],
            ),
            (
                "Text-Image Matching",
                [
                    RetrievedChunk(
                        chunk_id="layoutlmv2_tim_focus",
                        doc_id="layoutlmv2",
                        doc_name="layoutlmv2_2012.14740.pdf",
                        page_start=3,
                        page_end=3,
                        section_title="3 Experiments",
                        element_types=["paragraph"],
                        score=0.47,
                        text=(
                            "Text-Image Matching (TIM) is a coarse-grained cross-modality alignment task."
                        ),
                    )
                ],
            ),
        ],
    )
    llm_client = DummyLlmClient(
        '{"answerable": true, "answer": "1. Text-Image Alignment (TIA)\\n2. Text-Image Matching (TIM)", '
        '"cited_chunk_ids": ["layoutlmv2_tia_focus", "layoutlmv2_tim_focus"], "failure_reason": null}'
    )
    service = AnswerService(retriever=retriever, settings=settings, llm_client=llm_client)

    response = service.answer_question(question)
    prompt = llm_client.calls[0]["messages"][1]["content"]

    assert any("Text-Image Alignment" in call for call in retriever.calls[1:])
    assert any("Text-Image Matching" in call for call in retriever.calls[1:])
    assert "[layoutlmv2_tia_focus]" in prompt
    assert "[layoutlmv2_tim_focus]" in prompt
    assert response.answer == "1. Text-Image Alignment (TIA)\n2. Text-Image Matching (TIM)"
    assert {citation.chunk_id for citation in response.citations[:2]} == {
        "layoutlmv2_tia_focus",
        "layoutlmv2_tim_focus",
    }


def test_answer_service_reranks_llm_context_for_enumeration_questions(tmp_path):
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=1",
        ],
    )
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="layoutlmv2_generic",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=2,
                page_end=2,
                section_title="2 Approach",
                element_types=["heading", "paragraph"],
                score=0.52,
                text="In this section, we will introduce the multi-modal pre-training tasks of LayoutLMv2.",
            ),
            RetrievedChunk(
                chunk_id="layoutlmv2_specific",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=2,
                page_end=2,
                section_title="1 Introduction",
                element_types=["paragraph"],
                score=0.48,
                text=(
                    "For the pre-training strategies, we use two new training objectives. "
                    "The first is Text-Image Alignment (TIA). The second is Text-Image Matching (TIM)."
                ),
            ),
        ]
    )
    llm_client = DummyLlmClient(
        '{"answerable": true, "answer": "1. Text-Image Alignment (TIA)\\n2. Text-Image Matching (TIM)", '
        '"cited_chunk_ids": ["layoutlmv2_specific"], "failure_reason": null}'
    )
    service = AnswerService(retriever=retriever, settings=settings, llm_client=llm_client)

    response = service.answer_question("What are the two new pre-training tasks in LayoutLMv2?")

    prompt = llm_client.calls[0]["messages"][1]["content"]
    assert response.answerable is True
    assert "[layoutlmv2_specific]" in prompt
    assert "[layoutlmv2_generic]" not in prompt


def test_answer_service_reranks_citations_using_answer_content(tmp_path):
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=2",
        ],
    )
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="layoutlmv2_generic",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=2,
                page_end=2,
                section_title="2 Approach",
                element_types=["heading", "paragraph"],
                score=0.62,
                text="In this section, we will introduce the multi-modal pre-training tasks of LayoutLMv2.",
            ),
            RetrievedChunk(
                chunk_id="layoutlmv2_specific",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=2,
                page_end=2,
                section_title="1 Introduction",
                element_types=["paragraph"],
                score=0.45,
                text=(
                    "For the pre-training strategies, we use two new training objectives. "
                    "The first is Text-Image Alignment (TIA). The second is Text-Image Matching (TIM)."
                ),
            ),
            RetrievedChunk(
                chunk_id="layoutlmv2_tia",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=4,
                page_end=5,
                section_title="Text-Image Alignment",
                element_types=["paragraph"],
                score=0.43,
                text="Text-Image Alignment (TIA) is a fine-grained cross-modality alignment task.",
            ),
        ]
    )
    llm_client = DummyLlmClient(
        '{"answerable": true, "answer": "根据检索到的文档内容，1. Text-Image Alignment (TIA)\\n2. Text-Image Matching (TIM)", '
        '"cited_chunk_ids": ["layoutlmv2_generic"], "failure_reason": null}'
    )
    service = AnswerService(retriever=retriever, settings=settings, llm_client=llm_client)

    response = service.answer_question("LayoutLMv2新增的两个跨模态预训练任务是什么？")

    assert response.answer == "1. Text-Image Alignment (TIA)\n2. Text-Image Matching (TIM)"
    assert response.citations[0].chunk_id == "layoutlmv2_specific"


def test_answer_service_reranks_citations_for_utf8_chinese_enumeration_question(tmp_path):
    question = "LayoutLMv2\u65b0\u589e\u7684\u4e24\u4e2a\u8de8\u6a21\u6001\u9884\u8bad\u7ec3\u4efb\u52a1\u662f\u4ec0\u4e48\uff1f"
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "LLM_MODEL=gpt-test",
            "ANSWER_BACKEND=openai",
            "LLM_MAX_CONTEXT_CHUNKS=2",
        ],
    )
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="layoutlmv2_generic",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=2,
                page_end=2,
                section_title="2 Approach",
                element_types=["heading", "paragraph"],
                score=0.62,
                text="In this section, we will introduce the multi-modal pre-training tasks of LayoutLMv2.",
            ),
            RetrievedChunk(
                chunk_id="layoutlmv2_specific",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=2,
                page_end=2,
                section_title="1 Introduction",
                element_types=["paragraph"],
                score=0.45,
                text=(
                    "For the pre-training strategies, we use two new training objectives. "
                    "The first is Text-Image Alignment (TIA). The second is Text-Image Matching (TIM)."
                ),
            ),
            RetrievedChunk(
                chunk_id="layoutlmv2_tia",
                doc_id="layoutlmv2",
                doc_name="layoutlmv2_2012.14740.pdf",
                page_start=4,
                page_end=5,
                section_title="Text-Image Alignment",
                element_types=["paragraph"],
                score=0.43,
                text="Text-Image Alignment (TIA) is a fine-grained cross-modality alignment task.",
            ),
        ]
    )
    llm_client = DummyLlmClient(
        '{"answerable": true, "answer": "\\u6839\\u636e\\u68c0\\u7d22\\u5230\\u7684\\u6587\\u6863\\u5185\\u5bb9\\uff0c1. Text-Image Alignment (TIA)\\n2. Text-Image Matching (TIM)", '
        '"cited_chunk_ids": ["layoutlmv2_generic"], "failure_reason": null}'
    )
    service = AnswerService(retriever=retriever, settings=settings, llm_client=llm_client)

    response = service.answer_question(question)
    prompt = llm_client.calls[0]["messages"][1]["content"]

    assert "[layoutlmv2_specific]" in prompt
    assert response.answer == "1. Text-Image Alignment (TIA)\n2. Text-Image Matching (TIM)"
    assert response.citations[0].chunk_id == "layoutlmv2_specific"


def test_answer_service_describe_backend_reports_auto_fallback(tmp_path):
    settings = _build_settings(tmp_path)

    backend = AnswerService.describe_backend(settings)

    assert backend["configured_backend"] == "auto"
    assert backend["active_backend"] == "extractive"
    assert backend["reason"] == "llm_model_missing"


def test_answer_service_forced_openai_backend_requires_configuration(tmp_path):
    settings = _build_settings(
        tmp_path,
        extra_lines=[
            "ANSWER_BACKEND=openai",
            "LLM_MODEL=gpt-test",
        ],
    )
    retriever = DummyRetriever([])

    try:
        AnswerService(retriever=retriever, settings=settings)
    except LlmConfigurationError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected forced OpenAI backend to require API credentials")


def test_answer_service_relaxes_retrieval_threshold(tmp_path):
    settings = _build_settings(tmp_path)
    retriever = DummyRetriever(
        [
            RetrievedChunk(
                chunk_id="layoutlm_c0001",
                doc_id="layoutlm",
                doc_name="layoutlm_1912.13318.pdf",
                page_start=1,
                page_end=1,
                section_title="Abstract",
                element_types=["paragraph"],
                score=0.21,
                text="LayoutLM jointly models text and layout information for document understanding.",
            )
        ]
    )
    service = AnswerService(retriever=retriever, settings=settings)

    response = service.answer_question("LayoutLM在文档理解里最核心的建模对象是什么？")

    assert response.answerable is True
    assert retriever.last_score_threshold == 0.18
