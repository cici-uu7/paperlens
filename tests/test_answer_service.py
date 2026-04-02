from pathlib import Path
from types import SimpleNamespace

from app.core.config import get_settings
from app.models.schemas import RetrievalMetadata
from app.rag import AnswerService
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
