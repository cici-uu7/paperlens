import csv
import json

from app.core.config import get_settings
from app.services import manifest_service
from app.services.manifest_service import (
    MANIFEST_SCAN_LOG_NAME,
    build_manifest,
    build_manifest_artifacts,
    scan_raw_docs,
    scan_raw_docs_with_events,
)


def _make_settings(tmp_path):
    raw_docs_dir = tmp_path / "data" / "raw_docs"
    eval_dir = tmp_path / "data" / "eval"
    reports_dir = tmp_path / "reports"
    logs_dir = tmp_path / "logs"
    raw_docs_dir.mkdir(parents=True)
    eval_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    return get_settings(project_root=tmp_path, env_path=tmp_path / ".env")


def _write_source_manifest(settings, text):
    source_manifest = settings.eval_dir / "doc_manifest.csv"
    source_manifest.write_text(text, encoding="utf-8")
    return source_manifest


def _write_stub_pdf(path):
    path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")


def test_manifest_scan_merges_reference_metadata_and_writes_scan_log(tmp_path, monkeypatch):
    settings = _make_settings(tmp_path)
    sample_pdf = settings.raw_docs_dir / "sample.pdf"
    _write_stub_pdf(sample_pdf)

    source_manifest = _write_source_manifest(
        settings,
        "\n".join(
            [
                "filename,title,arxiv_id,source_url,focus,why_selected",
                "sample.pdf,Sample Title,1234.56789,https://example.invalid/sample,testing,seed dataset",
            ]
        ),
    )

    monkeypatch.setattr(
        manifest_service,
        "_read_page_count",
        lambda _path: (3, "ready", "", ""),
    )

    records = scan_raw_docs(settings=settings, source_manifest=source_manifest)
    assert len(records) == 1
    assert records[0].filename == "sample.pdf"
    assert records[0].title == "Sample Title"
    assert len(records[0].sha256) == 64
    assert records[0].status == "ready"
    assert records[0].page_count == 3

    artifacts = build_manifest_artifacts(
        settings=settings,
        output_path=settings.reports_dir / "doc_manifest_runtime.csv",
        source_manifest=source_manifest,
    )

    assert artifacts.manifest_path.exists()
    assert artifacts.scan_log_path == settings.logs_dir / MANIFEST_SCAN_LOG_NAME
    assert artifacts.scan_log_path.exists()
    assert artifacts.status_counts == {"ready": 1}

    with artifacts.manifest_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["filename"] == "sample.pdf"
    assert rows[0]["error_code"] == ""

    with artifacts.scan_log_path.open("r", encoding="utf-8") as handle:
        log_rows = [json.loads(line) for line in handle if line.strip()]
    assert log_rows == [
        {
            "level": "info",
            "scope": "file",
            "filename": "sample.pdf",
            "status": "ready",
            "error_code": "",
            "message": "ready",
        }
    ]

    output_path = build_manifest(
        settings=settings,
        output_path=settings.reports_dir / "doc_manifest_runtime_2.csv",
        source_manifest=source_manifest,
    )
    assert output_path.exists()


def test_manifest_scan_marks_invalid_pdf_header(tmp_path):
    settings = _make_settings(tmp_path)
    bad_pdf = settings.raw_docs_dir / "bad.pdf"
    bad_pdf.write_bytes(b"not-a-pdf")

    records = scan_raw_docs(settings=settings)
    assert len(records) == 1
    assert records[0].status == "invalid_pdf"
    assert records[0].error_code == "invalid_pdf_header"
    assert "Missing %PDF header" in records[0].error


def test_manifest_scan_marks_missing_runtime_dependency(tmp_path, monkeypatch):
    settings = _make_settings(tmp_path)
    sample_pdf = settings.raw_docs_dir / "sample.pdf"
    _write_stub_pdf(sample_pdf)

    monkeypatch.setattr(manifest_service, "fitz", None)
    records = scan_raw_docs(settings=settings)

    assert len(records) == 1
    assert records[0].status == "pending_pdf_runtime"
    assert records[0].error_code == "missing_dependency"
    assert "PyMuPDF" in records[0].error


def test_manifest_scan_maps_corrupted_pdf_runtime_error(tmp_path, monkeypatch):
    settings = _make_settings(tmp_path)
    sample_pdf = settings.raw_docs_dir / "broken.pdf"
    _write_stub_pdf(sample_pdf)

    class _BrokenDocument:
        def __enter__(self):
            raise RuntimeError("cannot open broken document")

        def __exit__(self, exc_type, exc, tb):
            return False

    class _BrokenFitz:
        @staticmethod
        def open(_path):
            return _BrokenDocument()

    monkeypatch.setattr(manifest_service, "fitz", _BrokenFitz())
    records = scan_raw_docs(settings=settings)

    assert len(records) == 1
    assert records[0].status == "corrupted_pdf"
    assert records[0].error_code == "corrupted_pdf"
    assert "broken document" in records[0].error


def test_manifest_scan_continues_after_file_access_error_and_logs(tmp_path, monkeypatch):
    settings = _make_settings(tmp_path)
    good_pdf = settings.raw_docs_dir / "good.pdf"
    blocked_pdf = settings.raw_docs_dir / "blocked.pdf"
    _write_stub_pdf(good_pdf)
    _write_stub_pdf(blocked_pdf)

    original_calculate_sha256 = manifest_service._calculate_sha256

    def _fake_calculate_sha256(path):
        if path.name == "blocked.pdf":
            raise PermissionError("access denied")
        return original_calculate_sha256(path)

    monkeypatch.setattr(manifest_service, "_calculate_sha256", _fake_calculate_sha256)
    monkeypatch.setattr(
        manifest_service,
        "_read_page_count",
        lambda _path: (1, "ready", "", ""),
    )

    records, events = scan_raw_docs_with_events(settings=settings)
    assert len(records) == 2

    record_by_name = {record.filename: record for record in records}
    assert record_by_name["good.pdf"].status == "ready"
    assert record_by_name["blocked.pdf"].status == "scan_error"
    assert record_by_name["blocked.pdf"].error_code == "file_access_error"
    assert "access denied" in record_by_name["blocked.pdf"].error

    blocked_events = [entry for entry in events if entry.filename == "blocked.pdf"]
    assert len(blocked_events) == 1
    assert blocked_events[0].level == "error"
    assert blocked_events[0].status == "scan_error"
    assert blocked_events[0].error_code == "file_access_error"
