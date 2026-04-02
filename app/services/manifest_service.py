"""Scan the demo PDFs and build a runtime manifest."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import Settings

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - exercised by environment, not logic
    fitz = None


MANIFEST_FIELDNAMES = [
    "filename",
    "title",
    "arxiv_id",
    "source_url",
    "focus",
    "why_selected",
    "source_path",
    "size_bytes",
    "sha256",
    "page_count",
    "status",
    "error_code",
    "error",
]

MANIFEST_SCAN_LOG_NAME = "manifest_scan.jsonl"


@dataclass
class ManifestRecord:
    filename: str
    title: str
    arxiv_id: str
    source_url: str
    focus: str
    why_selected: str
    source_path: str
    size_bytes: int
    sha256: str
    page_count: Optional[int]
    status: str
    error_code: str = ""
    error: str = ""

    def to_row(self) -> Dict[str, str]:
        return {
            "filename": self.filename,
            "title": self.title,
            "arxiv_id": self.arxiv_id,
            "source_url": self.source_url,
            "focus": self.focus,
            "why_selected": self.why_selected,
            "source_path": self.source_path,
            "size_bytes": str(self.size_bytes),
            "sha256": self.sha256,
            "page_count": "" if self.page_count is None else str(self.page_count),
            "status": self.status,
            "error_code": self.error_code,
            "error": self.error,
        }


@dataclass
class ManifestScanLogEntry:
    level: str
    scope: str
    filename: str
    status: str
    message: str
    error_code: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "level": self.level,
            "scope": self.scope,
            "filename": self.filename,
            "status": self.status,
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass
class ManifestBuildArtifacts:
    manifest_path: Path
    scan_log_path: Path
    status_counts: Dict[str, int]


def _calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_pdf_header(file_path: Path) -> bool:
    with file_path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def _classify_pdf_runtime_error(message: str) -> Tuple[str, str]:
    lowered = message.lower()
    if "pymupdf is not installed" in lowered:
        return "pending_pdf_runtime", "missing_dependency"
    corruption_markers = (
        "broken document",
        "broken xref",
        "cannot open broken document",
        "cannot open empty document",
        "cannot recognize version marker",
        "format error",
        "repairing pdf",
        "syntax error",
        "unexpected eof",
        "no objects found",
    )
    if any(marker in lowered for marker in corruption_markers):
        return "corrupted_pdf", "corrupted_pdf"
    return "parse_warning", "page_count_unavailable"


def _classify_scan_exception(exc: Exception) -> Tuple[str, str, str]:
    if isinstance(exc, PermissionError):
        return "scan_error", "file_access_error", f"File access error: {exc}"
    if isinstance(exc, OSError):
        return "scan_error", "file_io_error", f"File I/O error: {exc}"
    return "scan_error", "scan_error", f"Unexpected scan error: {exc}"


def _read_page_count(file_path: Path) -> Tuple[Optional[int], str, str, str]:
    if fitz is None:
        return None, "pending_pdf_runtime", "missing_dependency", "PyMuPDF is not installed"
    try:
        with fitz.open(file_path) as document:
            return int(document.page_count), "ready", "", ""
    except Exception as exc:  # pragma: no cover - depends on runtime PDF support
        status, error_code = _classify_pdf_runtime_error(str(exc))
        return None, status, error_code, str(exc)


def _safe_load_reference_metadata(
    manifest_path: Path,
) -> Tuple[Dict[str, Dict[str, str]], List[ManifestScanLogEntry]]:
    if not manifest_path.exists():
        return {}, []
    try:
        with manifest_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return (
                {row["filename"]: row for row in reader if row.get("filename")},
                [],
            )
    except Exception as exc:
        return (
            {},
            [
                ManifestScanLogEntry(
                    level="error",
                    scope="reference_metadata",
                    filename=manifest_path.name,
                    status="metadata_warning",
                    error_code="reference_manifest_unreadable",
                    message=f"Could not load reference metadata: {exc}",
                )
            ],
        )


def _log_level_for_status(status: str) -> str:
    if status == "ready":
        return "info"
    if status in {"pending_pdf_runtime", "invalid_pdf", "corrupted_pdf", "parse_warning"}:
        return "warning"
    return "error"


def _scan_single_pdf(
    pdf_path: Path,
    metadata: Dict[str, str],
) -> Tuple[ManifestRecord, ManifestScanLogEntry]:
    page_count: Optional[int] = None
    size_bytes = 0
    sha256 = ""
    status = "ready"
    error_code = ""
    error = ""

    try:
        size_bytes = pdf_path.stat().st_size
        sha256 = _calculate_sha256(pdf_path)
        if not _has_pdf_header(pdf_path):
            status = "invalid_pdf"
            error_code = "invalid_pdf_header"
            error = "Missing %PDF header"
        else:
            page_count, status, error_code, error = _read_page_count(pdf_path)
    except Exception as exc:
        status, error_code, error = _classify_scan_exception(exc)

    record = ManifestRecord(
        filename=pdf_path.name,
        title=metadata.get("title", ""),
        arxiv_id=metadata.get("arxiv_id", ""),
        source_url=metadata.get("source_url", ""),
        focus=metadata.get("focus", ""),
        why_selected=metadata.get("why_selected", ""),
        source_path=str(pdf_path),
        size_bytes=size_bytes,
        sha256=sha256,
        page_count=page_count,
        status=status,
        error_code=error_code,
        error=error,
    )
    entry = ManifestScanLogEntry(
        level=_log_level_for_status(status),
        scope="file",
        filename=pdf_path.name,
        status=status,
        error_code=error_code,
        message=error or "ready",
    )
    return record, entry


def scan_raw_docs_with_events(
    settings: Settings,
    source_manifest: Optional[Path] = None,
) -> Tuple[List[ManifestRecord], List[ManifestScanLogEntry]]:
    metadata_path = source_manifest or settings.eval_dir / "doc_manifest.csv"
    reference_metadata, metadata_events = _safe_load_reference_metadata(metadata_path)
    records: List[ManifestRecord] = []
    events: List[ManifestScanLogEntry] = list(metadata_events)

    if not settings.raw_docs_dir.exists():
        raise FileNotFoundError(f"Raw docs directory does not exist: {settings.raw_docs_dir}")

    for pdf_path in sorted(settings.raw_docs_dir.glob("*.pdf")):
        metadata = reference_metadata.get(pdf_path.name, {})
        record, entry = _scan_single_pdf(pdf_path=pdf_path, metadata=metadata)
        records.append(record)
        events.append(entry)

    return records, events


def scan_raw_docs(
    settings: Settings,
    source_manifest: Optional[Path] = None,
) -> List[ManifestRecord]:
    records, _ = scan_raw_docs_with_events(settings=settings, source_manifest=source_manifest)
    return records


def write_manifest(records: List[ManifestRecord], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_row())
    return output_path


def write_scan_log(entries: List[ManifestScanLogEntry], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    return output_path


def build_manifest_artifacts(
    settings: Settings,
    output_path: Optional[Path] = None,
    source_manifest: Optional[Path] = None,
    log_path: Optional[Path] = None,
) -> ManifestBuildArtifacts:
    records, events = scan_raw_docs_with_events(settings=settings, source_manifest=source_manifest)
    target = output_path or settings.reports_dir / "doc_manifest_runtime.csv"
    scan_log_target = log_path or settings.logs_dir / MANIFEST_SCAN_LOG_NAME
    manifest_path = write_manifest(records=records, output_path=target)
    scan_log_path = write_scan_log(entries=events, output_path=scan_log_target)
    status_counts = dict(Counter(record.status for record in records))
    return ManifestBuildArtifacts(
        manifest_path=manifest_path,
        scan_log_path=scan_log_path,
        status_counts=status_counts,
    )


def build_manifest(
    settings: Settings,
    output_path: Optional[Path] = None,
    source_manifest: Optional[Path] = None,
    log_path: Optional[Path] = None,
) -> Path:
    artifacts = build_manifest_artifacts(
        settings=settings,
        output_path=output_path,
        source_manifest=source_manifest,
        log_path=log_path,
    )
    return artifacts.manifest_path
