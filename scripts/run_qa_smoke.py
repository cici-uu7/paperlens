"""Run a small manual QA smoke validation for PaperLens."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.rag import AnswerService


DEFAULT_UNANSWERABLE_QUESTION = "这些论文在2026年4月的GitHub star分别是多少？"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small manual QA smoke validation for PaperLens.")
    parser.add_argument(
        "--question",
        action="append",
        default=[],
        help="Question to ask. Can be provided multiple times.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Optional retrieval top-k override.",
    )
    parser.add_argument(
        "--include-default-unanswerable",
        action="store_true",
        help="Append one synthetic unanswerable question.",
    )
    parser.add_argument(
        "--require-llm",
        action="store_true",
        help="Fail fast if the configured answer backend is not ready to use a real LLM.",
    )
    return parser.parse_args()


def _load_default_questions(settings, limit: int = 2) -> list[str]:
    questions_path = settings.eval_dir / "questions.csv"
    if not questions_path.exists():
        return []

    questions: list[str] = []
    with questions_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            question = (row.get("question") or "").strip()
            if question:
                questions.append(question)
            if len(questions) >= limit:
                break
    return questions


def main() -> int:
    args = parse_args()
    settings = get_settings(project_root=PROJECT_ROOT)
    backend_status = AnswerService.describe_backend(settings)
    print(
        "Answer backend: "
        + backend_status.get("active_backend", "unknown")
        + " | configured="
        + backend_status.get("configured_backend", "unknown")
        + " | model="
        + str(backend_status.get("llm_model") or "(none)")
    )
    if backend_status.get("message"):
        print("Backend note: " + str(backend_status["message"]))
    print()

    if args.require_llm and backend_status.get("active_backend") != "openai":
        raise RuntimeError(
            "Real LLM backend is not ready. "
            + str(backend_status.get("message") or backend_status.get("reason") or "unknown reason")
        )

    service = AnswerService.from_settings(settings)

    questions = list(args.question)
    if not questions:
        questions = _load_default_questions(settings)
    if args.include_default_unanswerable:
        questions.append(DEFAULT_UNANSWERABLE_QUESTION)
    if not questions:
        raise FileNotFoundError("No questions were provided and data/eval/questions.csv could not be read")

    for index, question in enumerate(questions, start=1):
        response = service.answer_question(question, top_k=args.top_k)
        print(f"[Q{index}] {question}")
        print(f"  answerable={response.answerable} failure_reason={response.failure_reason}")
        print(f"  answer={response.answer}")
        for citation in response.citations:
            print(
                "  citation="
                + citation.doc_name
                + f" p.{citation.page_num} "
                + citation.chunk_id
            )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
