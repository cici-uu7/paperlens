"""Scan the demo PDFs and build a runtime manifest."""

from __future__ import annotations

import csv
import hashlib
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
    "error",
]


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
            "error": self.error,
        }


def _calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_pdf_header(file_path: Path) -> bool:
    with file_path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def _read_page_count(file_path: Path) -> Tuple[Optional[int], Optional[str]]:
    if fitz is None:
        return None, "PyMuPDF is not installed"
    try:
        with fitz.open(file_path) as document:
            return int(document.page_count), None
    except Exception as exc:  # pragma: no cover - depends on runtime PDF support
        return None, str(exc)


def _load_reference_metadata(manifest_path: Path) -> Dict[str, Dict[str, str]]:
    if not manifest_path.exists():
        return {}
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {row["filename"]: row for row in reader if row.get("filename")}


def scan_raw_docs(
    settings: Settings,
    source_manifest: Optional[Path] = None,
) -> List[ManifestRecord]:
    metadata_path = source_manifest or settings.eval_dir / "doc_manifest.csv"
    reference_metadata = _load_reference_metadata(metadata_path)
    records: List[ManifestRecord] = []

    if not settings.raw_docs_dir.exists():
        raise FileNotFoundError(f"Raw docs directory does not exist: {settings.raw_docs_dir}")

    for pdf_path in sorted(settings.raw_docs_dir.glob("*.pdf")):
        metadata = reference_metadata.get(pdf_path.name, {})
        status = "ready"
        error = ""
        page_count: Optional[int] = None

        if not _has_pdf_header(pdf_path):
            status = "invalid_pdf"
            error = "Missing %PDF header"
        else:
            page_count, page_error = _read_page_count(pdf_path)
            if page_error:
                status = "pending_pdf_runtime" if "PyMuPDF" in page_error else "parse_warning"
                error = page_error

        records.append(
            ManifestRecord(
                filename=pdf_path.name,
                title=metadata.get("title", ""),
                arxiv_id=metadata.get("arxiv_id", ""),
                source_url=metadata.get("source_url", ""),
                focus=metadata.get("focus", ""),
                why_selected=metadata.get("why_selected", ""),
                source_path=str(pdf_path),
                size_bytes=pdf_path.stat().st_size,
                sha256=_calculate_sha256(pdf_path),
                page_count=page_count,
                status=status,
                error=error,
            )
        )

    return records


def write_manifest(records: List[ManifestRecord], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_row())
    return output_path


def build_manifest(
    settings: Settings,
    output_path: Optional[Path] = None,
    source_manifest: Optional[Path] = None,
) -> Path:
    records = scan_raw_docs(settings=settings, source_manifest=source_manifest)
    target = output_path or settings.reports_dir / "doc_manifest_runtime.csv"
    return write_manifest(records=records, output_path=target)
