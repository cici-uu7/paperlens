import csv

from app.core.config import get_settings
from app.services.manifest_service import build_manifest, scan_raw_docs


def test_manifest_scan_merges_reference_metadata(tmp_path):
    raw_docs_dir = tmp_path / "data" / "raw_docs"
    eval_dir = tmp_path / "data" / "eval"
    reports_dir = tmp_path / "reports"
    raw_docs_dir.mkdir(parents=True)
    eval_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)

    sample_pdf = raw_docs_dir / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")

    source_manifest = eval_dir / "doc_manifest.csv"
    source_manifest.write_text(
        "\n".join(
            [
                "filename,title,arxiv_id,source_url,focus,why_selected",
                "sample.pdf,Sample Title,1234.56789,https://example.invalid/sample,testing,seed dataset",
            ]
        ),
        encoding="utf-8",
    )

    settings = get_settings(project_root=tmp_path, env_path=tmp_path / ".env")
    records = scan_raw_docs(settings=settings, source_manifest=source_manifest)

    assert len(records) == 1
    assert records[0].filename == "sample.pdf"
    assert records[0].title == "Sample Title"
    assert len(records[0].sha256) == 64
    assert records[0].status in {"ready", "pending_pdf_runtime", "parse_warning"}

    output_path = build_manifest(
        settings=settings,
        output_path=reports_dir / "doc_manifest_runtime.csv",
        source_manifest=source_manifest,
    )

    assert output_path.exists()
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["filename"] == "sample.pdf"
    assert rows[0]["title"] == "Sample Title"
