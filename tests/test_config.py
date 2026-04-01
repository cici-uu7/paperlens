from pathlib import Path

from app.core.config import get_settings


def test_settings_loads_env_and_builds_paths(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-key",
                "OPENAI_BASE_URL=https://example.invalid/v1",
                "LLM_MODEL=gpt-test",
                "EMBEDDING_MODEL=text-embedding-test",
                "EMBEDDING_BACKEND=openai",
                "PARSER_BACKEND=opendataloader",
                "TOP_K=7",
                "CHUNK_MAX_CHARS=1600",
                "CHUNK_OVERLAP=240",
                "RETRIEVAL_SCORE_THRESHOLD=0.55",
            ]
        ),
        encoding="utf-8",
    )

    for name in [
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "LLM_MODEL",
        "OPENAI_MODEL",
        "EMBEDDING_MODEL",
        "EMBEDDING_BACKEND",
        "PARSER_BACKEND",
        "TOP_K",
        "CHUNK_MAX_CHARS",
        "CHUNK_OVERLAP",
        "RETRIEVAL_SCORE_THRESHOLD",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = get_settings(project_root=tmp_path, env_path=env_path)

    assert settings.project_root == tmp_path
    assert settings.raw_docs_dir == tmp_path / "data" / "raw_docs"
    assert settings.opendataloader_raw_dir == tmp_path / "data" / "parsed_docs" / "opendataloader_raw"
    assert settings.normalized_docs_dir == tmp_path / "data" / "parsed_docs" / "normalized"
    assert settings.reports_dir == tmp_path / "reports"
    assert settings.parser_backend == "opendataloader"
    assert settings.embedding_backend == "openai"
    assert settings.llm_model == "gpt-test"
    assert settings.embedding_model == "text-embedding-test"
    assert settings.top_k == 7
    assert settings.chunk_max_chars == 1600
    assert settings.chunk_overlap == 240
    assert settings.retrieval_score_threshold == 0.55


def test_settings_can_create_runtime_directories(tmp_path):
    settings = get_settings(project_root=tmp_path, env_path=tmp_path / ".env")
    created = settings.ensure_runtime_dirs()

    assert settings.raw_docs_dir in created
    assert settings.opendataloader_raw_dir in created
    assert settings.normalized_docs_dir in created
    assert settings.index_dir in created
    assert all(path.exists() for path in created)
    assert Path(settings.logs_dir).exists()
