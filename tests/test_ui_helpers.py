from app.core.config import get_settings
from ui.app import (
    UI_MODE_LOCAL,
    build_citation_evidence_blocks,
    build_local_snapshot,
    format_answer_source,
    format_citation_meta,
    format_failure_message,
    load_example_questions,
    parse_demo_query_params,
)


def test_build_local_snapshot_handles_missing_index(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    settings = get_settings(project_root=tmp_path, env_path=env_path)
    settings.ensure_runtime_dirs()

    snapshot = build_local_snapshot(settings)

    assert snapshot["health"]["index_built"] is False
    assert snapshot["documents"]["count"] == 0
    assert snapshot["indexed_count"] == 0
    assert snapshot["health"]["answer_backend"]["active_backend"] == "extractive"


def test_load_example_questions_reads_utf8_sig_csv(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    settings = get_settings(project_root=tmp_path, env_path=env_path)
    settings.ensure_runtime_dirs()

    questions_path = settings.eval_dir / "questions.csv"
    questions_path.write_text(
        "\n".join(
            [
                "question",
                "What is LayoutLM?",
                "Why is Self-RAG more flexible?",
            ]
        ),
        encoding="utf-8-sig",
    )

    questions = load_example_questions(settings, limit=2)

    assert len(questions) == 2
    assert questions[0] == "What is LayoutLM?"


def test_format_failure_message_maps_known_reasons():
    assert "insufficient" not in format_failure_message({"failure_reason": "insufficient_context"})
    assert "low_confidence" not in format_failure_message({"failure_reason": "low_confidence"})


def test_parse_demo_query_params_supports_aliases_and_list_values():
    parsed = parse_demo_query_params(
        {
            "question": ["What is LayoutLM?"],
            "autorun": ["true"],
            "top_k": ["6"],
            "mode": ["local"],
            "api_base_url": ["http://127.0.0.1:9000"],
        }
    )

    assert parsed == {
        "question": "What is LayoutLM?",
        "autorun": True,
        "top_k": 6,
        "mode": UI_MODE_LOCAL,
        "api_base_url": "http://127.0.0.1:9000",
    }


def test_format_citation_meta_and_bilingual_blocks():
    citation = {
        "doc_name": "rag_2005.11401.pdf",
        "source_title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "page_num": 6,
        "score": 0.3072,
        "quote_original": "RAG combines parametric memory with non-parametric memory.",
        "quote_translation": "RAG 将参数记忆与非参数记忆结合起来。",
        "quote_language": "en",
    }

    meta = format_citation_meta(citation)
    blocks = build_citation_evidence_blocks(citation)

    assert "PDF 文件名：rag_2005.11401.pdf" in meta
    assert "资料题目：Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" in meta
    assert "第 6 页" in meta
    assert "score：0.307" in meta
    assert blocks == [
        ("英文证据", "RAG combines parametric memory with non-parametric memory."),
        ("中文对照", "RAG 将参数记忆与非参数记忆结合起来。"),
    ]


def test_format_answer_source_uses_chinese_labels():
    assert format_answer_source("api") == "API"
    assert format_answer_source("local") == "本地服务"
