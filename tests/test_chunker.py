import json

from app.models.schemas import NormalizedDocument, NormalizedElement, NormalizedPage
from app.rag.chunker import chunk_normalized_document, write_chunk_records


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
