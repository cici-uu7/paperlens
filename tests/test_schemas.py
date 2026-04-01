from app.models.schemas import (
    AskResponse,
    ChunkRecord,
    Citation,
    NormalizedDocument,
    NormalizedElement,
    NormalizedPage,
    RetrievalMetadata,
)


def test_normalized_document_serializes_nested_elements():
    document = NormalizedDocument(
        doc_id="layoutlm_1912.13318",
        doc_name="layoutlm_1912.13318.pdf",
        title="LayoutLM",
        parser="pymupdf",
        page_count=1,
        pages=[
            NormalizedPage(
                page_num=1,
                elements=[
                    NormalizedElement(
                        element_id="p1_e1",
                        type="heading",
                        text="LayoutLM",
                        bbox=[0.0, 0.0, 100.0, 32.0],
                        section_path=["Title"],
                    )
                ],
            )
        ],
        metadata={"source_path": "data/raw_docs/layoutlm_1912.13318.pdf"},
    )

    payload = document.to_dict()

    assert payload["doc_name"] == "layoutlm_1912.13318.pdf"
    assert payload["pages"][0]["page_num"] == 1
    assert payload["pages"][0]["elements"][0]["type"] == "heading"
    assert payload["metadata"]["source_path"].endswith("layoutlm_1912.13318.pdf")


def test_chunk_and_answer_response_are_serializable():
    chunk = ChunkRecord(
        chunk_id="layoutlm_c0001",
        doc_id="layoutlm_1912.13318",
        doc_name="layoutlm_1912.13318.pdf",
        page_start=1,
        page_end=1,
        text="LayoutLM jointly models text and layout.",
        section_title="Abstract",
        element_types=["paragraph"],
    )
    response = AskResponse(
        question="LayoutLM models what?",
        answer="It jointly models text and layout.",
        answerable=True,
        citations=[
            Citation(
                doc_name="layoutlm_1912.13318.pdf",
                page_num=1,
                chunk_id=chunk.chunk_id,
                quote="jointly models text and layout",
                score=0.91,
            )
        ],
        retrieval=RetrievalMetadata(top_k=5, hit_count=1, latency_ms=12.5),
    )

    chunk_payload = chunk.to_dict()
    response_payload = response.to_dict()

    assert chunk_payload["char_count"] == len(chunk.text)
    assert response_payload["citations"][0]["chunk_id"] == "layoutlm_c0001"
    assert response_payload["retrieval"]["top_k"] == 5
    assert response_payload["answerable"] is True
