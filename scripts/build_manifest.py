"""Build a runtime manifest from the demo PDFs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.manifest_service import build_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a runtime manifest for PaperLens PDFs.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output CSV path. Defaults to reports/doc_manifest_runtime.csv.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings(project_root=PROJECT_ROOT)
    output_path = build_manifest(settings=settings, output_path=args.output)
    print(f"Wrote runtime manifest to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
