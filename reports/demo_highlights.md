# PaperLens Demo Highlights

## Demo Assets

- UI screenshot: `screenshots/paperlens-demo-ui.png`
- Evaluation summary: `reports/eval_summary.md`
- Evaluation CSV: `reports/eval_results.csv`
- Evaluation run log: `reports/run_log.txt`

## Current Snapshot

- 10 source PDFs are indexed for retrieval.
- The demo supports FastAPI plus Streamlit.
- The Streamlit UI now supports autorun demo mode, refusal handling, and citation display.
- The latest evaluation run completed all 20 questions with no runtime errors.

## Metrics From The Latest Run

- answered: `18 / 20`
- refused: `2 / 20`
- errors: `0 / 20`
- citation rate: `90.00%`
- expected doc hit rate: `100.00%`
- answerability match rate: `100.00%`

## Notes For Final Packaging

- The current answer quality is usable for demo purposes, but still relies mainly on the extractive fallback path.
- The remaining major technical debt before final polish is `T018`, the chunk-quality improvement task.
- If real LLM credentials become available, rerun the smoke QA, UI demo, and full evaluation to refresh the artifacts.
