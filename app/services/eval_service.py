"""Evaluation service for the PaperLens QA pipeline."""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import Settings
from app.models.schemas import Citation
from app.rag.answer_service import AnswerService


@dataclass(frozen=True)
class EvaluationQuestion:
    question_id: str
    question_type: str
    answerability: str
    question: str
    gold_doc: str
    gold_page_hint: str
    gold_answer: str

    @property
    def expects_answer(self) -> bool:
        return self.answerability.strip().lower() == "answerable"


@dataclass
class EvaluationResult:
    question_id: str
    question_type: str
    expected_answerability: str
    question: str
    predicted_answer: str
    answerable: bool
    status: str
    citations: List[Citation] = field(default_factory=list)
    latency_ms: float = 0.0
    expected_doc: str = ""
    expected_page_hint: str = ""
    gold_answer: str = ""
    failure_reason: str = ""
    error: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def citation_count(self) -> int:
        return len(self.citations)

    @property
    def hit_docs(self) -> List[str]:
        names: List[str] = []
        for citation in self.citations:
            if citation.doc_name and citation.doc_name not in names:
                names.append(citation.doc_name)
        return names

    @property
    def expected_doc_hit(self) -> bool:
        expected_docs = [part.strip() for part in self.expected_doc.split("|") if part.strip()]
        if not expected_docs or expected_docs == ["NOT_FOUND"]:
            return not self.answerable and self.status != "error"
        if "NOT_FOUND" in expected_docs:
            return not self.answerable and self.status != "error"
        return any(expected_doc in self.hit_docs for expected_doc in expected_docs)

    @property
    def answerability_match(self) -> bool:
        expected = self.expected_answerability.strip().lower() == "answerable"
        return expected == self.answerable

    def to_csv_row(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question_type": self.question_type,
            "expected_answerability": self.expected_answerability,
            "question": self.question,
            "predicted_answer": self.predicted_answer,
            "answerable": self.answerable,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "citation_count": self.citation_count,
            "hit_docs": json.dumps(self.hit_docs, ensure_ascii=False),
            "expected_doc": self.expected_doc,
            "expected_page_hint": self.expected_page_hint,
            "expected_doc_hit": self.expected_doc_hit,
            "answerability_match": self.answerability_match,
            "failure_reason": self.failure_reason,
            "error": self.error,
            "gold_answer": self.gold_answer,
            "citation_payload": json.dumps(
                [citation.to_dict() for citation in self.citations],
                ensure_ascii=False,
            ),
            "notes": " | ".join(self.notes),
        }


@dataclass(frozen=True)
class EvaluationSummary:
    total_questions: int
    answered_count: int
    refusal_count: int
    error_count: int
    cited_count: int
    doc_hit_count: int
    answerability_match_count: int
    avg_latency_ms: float

    @property
    def answer_rate(self) -> float:
        return self.answered_count / self.total_questions if self.total_questions else 0.0

    @property
    def refusal_rate(self) -> float:
        return self.refusal_count / self.total_questions if self.total_questions else 0.0

    @property
    def error_rate(self) -> float:
        return self.error_count / self.total_questions if self.total_questions else 0.0

    @property
    def citation_rate(self) -> float:
        return self.cited_count / self.total_questions if self.total_questions else 0.0

    @property
    def doc_hit_rate(self) -> float:
        return self.doc_hit_count / self.total_questions if self.total_questions else 0.0

    @property
    def answerability_match_rate(self) -> float:
        return (
            self.answerability_match_count / self.total_questions
            if self.total_questions
            else 0.0
        )


class EvaluationService:
    def __init__(self, answer_service: AnswerService, settings: Settings) -> None:
        self.answer_service = answer_service
        self.settings = settings

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        answer_service: Optional[AnswerService] = None,
    ) -> "EvaluationService":
        return cls(
            answer_service=answer_service or AnswerService.from_settings(settings),
            settings=settings,
        )

    def load_questions(self, questions_path: Optional[Path] = None) -> List[EvaluationQuestion]:
        path = Path(questions_path) if questions_path else self.settings.eval_dir / "questions.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            questions = [
                EvaluationQuestion(
                    question_id=(row.get("id") or "").strip(),
                    question_type=(row.get("question_type") or "").strip(),
                    answerability=(row.get("answerability") or "").strip(),
                    question=(row.get("question") or "").strip(),
                    gold_doc=(row.get("gold_doc") or "").strip(),
                    gold_page_hint=(row.get("gold_page_hint") or "").strip(),
                    gold_answer=(row.get("gold_answer") or "").strip(),
                )
                for row in reader
                if (row.get("id") or "").strip() and (row.get("question") or "").strip()
            ]
        return questions

    def evaluate_question(
        self,
        question: EvaluationQuestion,
        top_k: Optional[int] = None,
    ) -> EvaluationResult:
        started = time.perf_counter()
        try:
            response = self.answer_service.answer_question(question.question, top_k=top_k)
            latency_ms = (time.perf_counter() - started) * 1000.0
            result = EvaluationResult(
                question_id=question.question_id,
                question_type=question.question_type,
                expected_answerability=question.answerability,
                question=question.question,
                predicted_answer=response.answer,
                answerable=response.answerable,
                status="answered" if response.answerable else "refused",
                citations=list(response.citations),
                latency_ms=latency_ms,
                expected_doc=question.gold_doc,
                expected_page_hint=question.gold_page_hint,
                gold_answer=question.gold_answer,
                failure_reason=response.failure_reason or "",
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            result = EvaluationResult(
                question_id=question.question_id,
                question_type=question.question_type,
                expected_answerability=question.answerability,
                question=question.question,
                predicted_answer="",
                answerable=False,
                status="error",
                citations=[],
                latency_ms=latency_ms,
                expected_doc=question.gold_doc,
                expected_page_hint=question.gold_page_hint,
                gold_answer=question.gold_answer,
                error=str(exc),
                notes=["exception"],
            )
            return result

        if not result.answerability_match:
            result.notes.append("answerability_mismatch")
        if not result.expected_doc_hit:
            result.notes.append("expected_doc_miss")
        if result.status == "refused" and not question.expects_answer:
            result.notes.append("expected_refusal")
        return result

    def evaluate_questions(
        self,
        questions: Sequence[EvaluationQuestion],
        top_k: Optional[int] = None,
    ) -> List[EvaluationResult]:
        return [self.evaluate_question(question, top_k=top_k) for question in questions]

    @staticmethod
    def summarize(results: Sequence[EvaluationResult]) -> EvaluationSummary:
        total = len(results)
        answered_count = sum(1 for result in results if result.status == "answered")
        refusal_count = sum(1 for result in results if result.status == "refused")
        error_count = sum(1 for result in results if result.status == "error")
        cited_count = sum(1 for result in results if result.citation_count > 0)
        doc_hit_count = sum(1 for result in results if result.expected_doc_hit)
        answerability_match_count = sum(1 for result in results if result.answerability_match)
        avg_latency_ms = (
            sum(result.latency_ms for result in results) / total if total else 0.0
        )
        return EvaluationSummary(
            total_questions=total,
            answered_count=answered_count,
            refusal_count=refusal_count,
            error_count=error_count,
            cited_count=cited_count,
            doc_hit_count=doc_hit_count,
            answerability_match_count=answerability_match_count,
            avg_latency_ms=avg_latency_ms,
        )

    def write_results_csv(
        self,
        results: Sequence[EvaluationResult],
        output_path: Optional[Path] = None,
    ) -> Path:
        path = Path(output_path) if output_path else self.settings.reports_dir / "eval_results.csv"
        fieldnames = [
            "question_id",
            "question_type",
            "expected_answerability",
            "question",
            "predicted_answer",
            "answerable",
            "status",
            "latency_ms",
            "citation_count",
            "hit_docs",
            "expected_doc",
            "expected_page_hint",
            "expected_doc_hit",
            "answerability_match",
            "failure_reason",
            "error",
            "gold_answer",
            "citation_payload",
            "notes",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                writer.writerow(result.to_csv_row())
        return path

    def write_summary_markdown(
        self,
        results: Sequence[EvaluationResult],
        summary: EvaluationSummary,
        output_path: Optional[Path] = None,
    ) -> Path:
        path = Path(output_path) if output_path else self.settings.reports_dir / "eval_summary.md"
        review_rows = [result for result in results if result.status == "error" or result.notes]
        lines = [
            "# PaperLens Evaluation Summary",
            "",
            "## Metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Total questions | {summary.total_questions} |",
            f"| Answered | {summary.answered_count} |",
            f"| Refused | {summary.refusal_count} |",
            f"| Errors | {summary.error_count} |",
            f"| Answer rate | {summary.answer_rate:.2%} |",
            f"| Refusal rate | {summary.refusal_rate:.2%} |",
            f"| Citation rate | {summary.citation_rate:.2%} |",
            f"| Expected doc hit rate | {summary.doc_hit_rate:.2%} |",
            f"| Answerability match rate | {summary.answerability_match_rate:.2%} |",
            f"| Avg latency (ms) | {summary.avg_latency_ms:.2f} |",
            "",
            "## Review Queue",
            "",
        ]
        if review_rows:
            lines.extend(
                [
                    "| ID | Status | Expected Doc | Hit Docs | Notes |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for result in review_rows:
                hit_docs = ", ".join(result.hit_docs) or "-"
                notes = ", ".join(result.notes) if result.notes else (result.error or "-")
                lines.append(
                    f"| {result.question_id} | {result.status} | {result.expected_doc or '-'} | {hit_docs} | {notes} |"
                )
        else:
            lines.append("No review items. All questions were recorded without error.")
        lines.extend(
            [
                "",
                "## Artifacts",
                "",
                f"- Results CSV: `{self.settings.reports_dir / 'eval_results.csv'}`",
                f"- Summary Markdown: `{path}`",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def write_run_log(
        self,
        results: Sequence[EvaluationResult],
        output_path: Optional[Path] = None,
    ) -> Path:
        path = Path(output_path) if output_path else self.settings.reports_dir / "run_log.txt"
        lines = []
        for result in results:
            lines.append(
                " | ".join(
                    [
                        result.question_id,
                        result.status,
                        f"latency_ms={result.latency_ms:.2f}",
                        f"hit_docs={','.join(result.hit_docs) or '-'}",
                        f"failure_reason={result.failure_reason or '-'}",
                        f"error={result.error or '-'}",
                    ]
                )
            )
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path

    def run_full_evaluation(
        self,
        top_k: Optional[int] = None,
        questions_path: Optional[Path] = None,
        results_path: Optional[Path] = None,
        summary_path: Optional[Path] = None,
        run_log_path: Optional[Path] = None,
    ) -> Tuple[List[EvaluationResult], EvaluationSummary, Dict[str, Path]]:
        questions = self.load_questions(questions_path)
        results = self.evaluate_questions(questions, top_k=top_k)
        summary = self.summarize(results)
        written_paths = {
            "results_csv": self.write_results_csv(results, results_path),
            "summary_md": self.write_summary_markdown(results, summary, summary_path),
            "run_log": self.write_run_log(results, run_log_path),
        }
        return results, summary, written_paths
