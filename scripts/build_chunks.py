"""Build chunk JSONL files from normalized PaperLens documents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.rag.chunker import chunk_normalized_document, load_normalized_document, write_chunk_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PaperLens chunk JSONL files from normalized docs.")
    parser.add_argument(
        "--normalized-dir",
        type=Path,
        default=None,
        help="Optional normalized-doc directory. Defaults to data/parsed_docs/normalized.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to data/chunks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings(project_root=PROJECT_ROOT)
    normalized_dir = args.normalized_dir or settings.normalized_docs_dir
    output_dir = args.output_dir or settings.chunk_dir

    normalized_files = sorted(Path(normalized_dir).glob("*.json"))
    if not normalized_files:
        raise FileNotFoundError(f"No normalized documents found in {normalized_dir}")

    chunk_files = 0
    total_chunks = 0
    for normalized_file in normalized_files:
        document = load_normalized_document(normalized_file)
        records = chunk_normalized_document(
            document,
            max_chars=settings.chunk_max_chars,
            overlap=settings.chunk_overlap,
        )
        write_chunk_records(records, Path(output_dir) / f"{document.doc_id}.jsonl")
        chunk_files += 1
        total_chunks += len(records)

    print(
        "chunk_files="
        + str(chunk_files)
        + " chunk_count="
        + str(total_chunks)
        + " output_dir="
        + str(output_dir)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
