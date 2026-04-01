from app.core.config import get_settings
from app.models.schemas import ChunkRecord
from app.rag import HashingEmbedder, IndexNotBuiltError, IndexStore, Retriever


def test_retriever_returns_layoutlm_chunk_for_mixed_language_query(tmp_path):
    records = [
        ChunkRecord(
            chunk_id="layoutlm_c0001",
            doc_id="layoutlm",
            doc_name="layoutlm_1912.13318.pdf",
            page_start=1,
            page_end=1,
            text="LayoutLM jointly models text and layout information for document understanding.",
            section_title="Abstract",
            element_types=["paragraph"],
        ),
        ChunkRecord(
            chunk_id="donut_c0001",
            doc_id="donut",
            doc_name="donut_2111.15664.pdf",
            page_start=3,
            page_end=3,
            text="Donut is an OCR-free document understanding transformer.",
            section_title="Introduction",
            element_types=["paragraph"],
        ),
    ]

    embedder = HashingEmbedder(dim=128)
    vectors = embedder.embed_texts(record.text for record in records)
    store = IndexStore.build(records=records, vectors=vectors)
    store.save(tmp_path)

    retriever = Retriever(index_store=store, embedder=embedder, default_top_k=2, score_threshold=0.0)
    hits, metadata = retriever.retrieve("LayoutLM在文档理解里建模什么？", top_k=1)

    assert hits
    assert hits[0].chunk_id == "layoutlm_c0001"
    assert hits[0].doc_name == "layoutlm_1912.13318.pdf"
    assert metadata.hit_count == 1


def test_retriever_from_settings_raises_when_index_missing(tmp_path):
    settings = get_settings(project_root=tmp_path, env_path=tmp_path / ".env")

    try:
        Retriever.from_settings(settings)
    except IndexNotBuiltError as exc:
        assert "build_info.json" in str(exc)
    else:
        raise AssertionError("Expected IndexNotBuiltError when index files are absent")
