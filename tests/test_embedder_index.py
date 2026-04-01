from app.models.schemas import ChunkRecord
from app.rag.embedder import HashingEmbedder
from app.rag.index_store import IndexStore


def test_hashing_embedder_is_deterministic():
    embedder = HashingEmbedder(dim=64)

    first = embedder.embed_query("paperlens retrieval with citations")
    second = embedder.embed_query("paperlens retrieval with citations")
    third = embedder.embed_query("vision-language document retrieval")

    assert first == second
    assert first != third
    assert len(first) == 64


def test_index_store_save_load_and_search(tmp_path):
    records = [
        ChunkRecord(
            chunk_id="doc1_c0001",
            doc_id="doc1",
            doc_name="doc1.pdf",
            page_start=1,
            page_end=1,
            text="PaperLens uses structured retrieval with page citations.",
        ),
        ChunkRecord(
            chunk_id="doc2_c0001",
            doc_id="doc2",
            doc_name="doc2.pdf",
            page_start=2,
            page_end=2,
            text="Vision language models support multimodal document retrieval.",
        ),
    ]

    embedder = HashingEmbedder(dim=128)
    vectors = embedder.embed_texts(record.text for record in records)
    store = IndexStore.build(records=records, vectors=vectors)
    store.save(tmp_path)

    loaded = IndexStore.load(tmp_path)
    hits = loaded.search(embedder.embed_query("structured retrieval citations"), top_k=1)

    assert hits
    assert hits[0].chunk.chunk_id == "doc1_c0001"
    assert (tmp_path / "build_info.json").exists()
    assert (tmp_path / "chunk_metadata.jsonl").exists()
