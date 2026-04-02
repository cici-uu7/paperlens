import json

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import get_settings
from app.models.schemas import AskResponse, Citation, RetrievalMetadata


class DummyAnswerService:
    def answer_question(self, question: str, top_k=None):
        return AskResponse(
            question=question,
            answer="Grounded demo answer.",
            answerable=True,
            citations=[
                Citation(
                    doc_name="layoutlm_1912.13318.pdf",
                    page_num=2,
                    chunk_id="layoutlm_c0001",
                    quote="jointly model text and layout",
                    score=0.88,
                )
            ],
            retrieval=RetrievalMetadata(top_k=top_k or 5, hit_count=1, latency_ms=9.2),
        )


def _build_settings(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    settings = get_settings(project_root=tmp_path, env_path=env_path)
    settings.ensure_runtime_dirs()
    return settings


def _write_manifest(settings):
    manifest_path = settings.reports_dir / "doc_manifest_runtime.csv"
    manifest_path.write_text(
        "\n".join(
            [
                "filename,title,page_count,status",
                "layoutlm_1912.13318.pdf,LayoutLM,9,ready",
                "rag_2005.11401.pdf,RAG,5,ready",
            ]
        ),
        encoding="utf-8",
    )


def _write_index_metadata(settings):
    build_info = settings.index_dir / "build_info.json"
    chunk_metadata = settings.index_dir / "chunk_metadata.jsonl"
    build_info.write_text(
        json.dumps({"backend": "json", "chunk_count": 1, "vector_dim": 1024}),
        encoding="utf-8",
    )
    chunk_metadata.write_text(
        json.dumps(
            {
                "chunk_id": "layoutlm_c0001",
                "doc_id": "layoutlm",
                "doc_name": "layoutlm_1912.13318.pdf",
                "page_start": 2,
                "page_end": 2,
                "text": "LayoutLM jointly models text and layout.",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_health_endpoint_reports_status(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings=settings, answer_service_factory=lambda: DummyAnswerService())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["index_built"] is False
    assert payload["answer_backend"]["active_backend"] == "extractive"


def test_documents_endpoint_marks_indexed_documents(tmp_path):
    settings = _build_settings(tmp_path)
    _write_manifest(settings)
    _write_index_metadata(settings)
    app = create_app(settings=settings, answer_service_factory=lambda: DummyAnswerService())
    client = TestClient(app)

    response = client.get("/documents")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["documents"][0]["doc_name"] == "layoutlm_1912.13318.pdf"
    assert payload["documents"][0]["indexed"] is True
    assert payload["documents"][1]["indexed"] is False


def test_ask_endpoint_returns_answer_service_payload(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings=settings, answer_service_factory=lambda: DummyAnswerService())
    client = TestClient(app)

    response = client.post("/ask", json={"question": "What does LayoutLM model?", "top_k": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answerable"] is True
    assert payload["question"] == "What does LayoutLM model?"
    assert payload["citations"][0]["chunk_id"] == "layoutlm_c0001"
