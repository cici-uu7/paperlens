from app.core.config import get_settings
from ui.app import (
    build_local_snapshot,
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
                "LayoutLM在文档理解里最核心的建模对象是什么？",
                "Self-RAG为什么比固定检索式RAG更灵活？",
            ]
        ),
        encoding="utf-8-sig",
    )

    questions = load_example_questions(settings, limit=2)

    assert len(questions) == 2
    assert questions[0].startswith("LayoutLM")


def test_format_failure_message_maps_known_reasons():
    assert "拒答" in format_failure_message({"failure_reason": "insufficient_context"})
    assert "相关性过弱" in format_failure_message({"failure_reason": "low_confidence"})


def test_parse_demo_query_params_supports_aliases_and_list_values():
    parsed = parse_demo_query_params(
        {
            "question": ["LayoutLM是什么？"],
            "autorun": ["true"],
            "top_k": ["6"],
            "mode": ["local"],
        }
    )

    assert parsed == {
        "question": "LayoutLM是什么？",
        "autorun": True,
        "top_k": 6,
        "mode": "本地服务",
    }
