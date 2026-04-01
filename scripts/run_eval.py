"""Run the PaperLens evaluation suite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.services.eval_service import EvaluationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PaperLens evaluation")
    parser.add_argument("--questions", type=Path, default=None, help="Optional path to questions.csv")
    parser.add_argument("--results", type=Path, default=None, help="Optional output path for eval_results.csv")
    parser.add_argument("--summary", type=Path, default=None, help="Optional output path for eval_summary.md")
    parser.add_argument("--run-log", type=Path, default=None, help="Optional output path for run_log.txt")
    parser.add_argument("--top-k", type=int, default=None, help="Override retrieval top-k during evaluation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    service = EvaluationService.from_settings(settings)
    results, summary, paths = service.run_full_evaluation(
        top_k=args.top_k,
        questions_path=args.questions,
        results_path=args.results,
        summary_path=args.summary,
        run_log_path=args.run_log,
    )

    print(f"questions={len(results)}")
    print(f"answered={summary.answered_count}")
    print(f"refused={summary.refusal_count}")
    print(f"errors={summary.error_count}")
    print(f"citation_rate={summary.citation_rate:.2%}")
    print(f"doc_hit_rate={summary.doc_hit_rate:.2%}")
    print(f"avg_latency_ms={summary.avg_latency_ms:.2f}")
    for name, path in paths.items():
        print(f"{name}={path}")


if __name__ == "__main__":
    main()
