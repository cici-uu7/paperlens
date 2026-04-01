import json

from app.models.schemas import NormalizedDocument, NormalizedElement, NormalizedPage
from app.rag.chunker import chunk_normalized_document, load_chunk_records, write_chunk_records


def test_chunker_generates_stable_chunk_ids_and_metadata(tmp_path):
    document = NormalizedDocument(
        doc_id="demo_doc",
        doc_name="demo.pdf",
        title="Demo",
        parser="pymupdf",
        page_count=2,
        pages=[
            NormalizedPage(
                page_num=1,
                elements=[
                    NormalizedElement(element_id="p1_e1", type="heading", text="Section One"),
                    NormalizedElement(
                        element_id="p1_e2",
                        type="paragraph",
                        text="This is a test paragraph that should stay with its heading.",
                    ),
                ],
            ),
            NormalizedPage(
                page_num=2,
                elements=[
                    NormalizedElement(
                        element_id="p2_e1",
                        type="paragraph",
                        text="Another paragraph with enough content to force the chunker to split the text into more than one record when the max size is small.",
                    )
                ],
            ),
        ],
    )

    records = chunk_normalized_document(document, max_chars=80, overlap=20)

    assert len(records) >= 2
    assert records[0].chunk_id == "demo_doc_c0001"
    assert records[0].section_title == "Section One"
    assert records[0].page_start == 1
    assert records[-1].page_end == 2
    assert all(record.char_count <= 80 for record in records)

    output_path = write_chunk_records(records, tmp_path / "chunks.jsonl")
    lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])

    assert output_path.exists()
    assert payload["chunk_id"] == "demo_doc_c0001"
    assert payload["doc_name"] == "demo.pdf"
    loaded = load_chunk_records(output_path)
    assert loaded[0].chunk_id == "demo_doc_c0001"


def test_chunker_splits_long_paragraph_without_oversized_chunks():
    long_text = " ".join(
        [
            "LayoutLMv2 introduces multi-modal pre-training for visually rich documents."
            for _ in range(18)
        ]
    )
    document = NormalizedDocument(
        doc_id="long_doc",
        doc_name="long.pdf",
        title="Long",
        parser="structured",
        page_count=1,
        pages=[
            NormalizedPage(
                page_num=1,
                elements=[
                    NormalizedElement(element_id="p1_e1", type="heading", text="Overview"),
                    NormalizedElement(element_id="p1_e2", type="paragraph", text=long_text),
                ],
            )
        ],
    )

    records = chunk_normalized_document(document, max_chars=220, overlap=40)

    assert len(records) >= 3
    assert all(record.char_count <= 220 for record in records)
    assert all(record.section_title == "Overview" for record in records)


def test_chunker_preserves_cross_page_page_span_in_single_chunk():
    document = NormalizedDocument(
        doc_id="cross_page",
        doc_name="cross.pdf",
        title="Cross",
        parser="structured",
        page_count=2,
        pages=[
            NormalizedPage(
                page_num=1,
                elements=[
                    NormalizedElement(element_id="p1_e1", type="heading", text="Method"),
                    NormalizedElement(
                        element_id="p1_e2",
                        type="paragraph",
                        text="The first half of the explanation stays on page one and should remain connected.",
                    ),
                ],
            ),
            NormalizedPage(
                page_num=2,
                elements=[
                    NormalizedElement(
                        element_id="p2_e1",
                        type="paragraph",
                        text="The second half continues on page two without a new heading, so the chunk should span both pages.",
                    )
                ],
            ),
        ],
    )

    records = chunk_normalized_document(document, max_chars=400, overlap=40)

    assert len(records) == 1
    assert records[0].page_start == 1
    assert records[0].page_end == 2
    assert records[0].metadata["spans_multiple_pages"] is True


def test_chunker_splits_table_rows_into_table_chunks():
    table_text = "\n".join(
        [
            "Model | Dataset | Score",
            "LayoutLMv2 | FUNSD | 0.842",
            "LayoutLMv3 | FUNSD | 0.879",
            "DocFormer | CORD | 0.944",
            "Donut | DocVQA | 0.672",
        ]
    )
    document = NormalizedDocument(
        doc_id="table_doc",
        doc_name="table.pdf",
        title="Table",
        parser="structured",
        page_count=1,
        pages=[
            NormalizedPage(
                page_num=1,
                elements=[
                    NormalizedElement(element_id="p1_e1", type="heading", text="Results"),
                    NormalizedElement(element_id="p1_e2", type="table", text=table_text),
                ],
            )
        ],
    )

    records = chunk_normalized_document(document, max_chars=60, overlap=0)

    assert len(records) >= 2
    assert all(record.char_count <= 60 for record in records)
    assert all("table" in record.element_types for record in records)
    assert all(record.metadata["chunk_kind"] == "table" for record in records)
