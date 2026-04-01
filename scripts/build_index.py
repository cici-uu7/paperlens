"""Build a local retrieval index from chunk files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.rag.chunker import load_chunk_records
from app.rag.embedder import build_embedder
from app.rag.index_store import IndexStore


def _embedding_text_for_record(record) -> str:
    doc_hint = Path(record.doc_name).stem.replace("_", " ").replace("-", " ")
    parts = [doc_hint]
    if record.section_title:
        parts.append(record.section_title)
    parts.append(record.text)
    return "\n".join(part for part in parts if part)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local PaperLens index from chunk JSONL files.")
    parser.add_argument(
        "--chunk-dir",
        type=Path,
        default=None,
        help="Optional chunk directory. Defaults to data/chunks.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional index output directory. Defaults to data/indexes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings(project_root=PROJECT_ROOT)
    chunk_dir = args.chunk_dir or settings.chunk_dir
    output_dir = args.output_dir or settings.index_dir

    chunk_files = sorted(Path(chunk_dir).glob("*.jsonl"))
    if not chunk_files:
        raise FileNotFoundError(f"No chunk files found in {chunk_dir}")

    records = []
    for chunk_file in chunk_files:
        records.extend(load_chunk_records(chunk_file))

    embedder = build_embedder(settings)
    vectors = embedder.embed_texts(_embedding_text_for_record(record) for record in records)
    store = IndexStore.build(records=records, vectors=vectors)
    store.save(output_dir)

    print(
        "index_backend="
        + store.backend
        + " chunk_files="
        + str(len(chunk_files))
        + " chunk_count="
        + str(len(records))
        + " output_dir="
        + str(output_dir)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
