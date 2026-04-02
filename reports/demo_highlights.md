# PaperLens Demo Highlights

## Demo Assets

- UI screenshot: `screenshots/paperlens-demo-ui.png`
- Evaluation summary: `reports/eval_summary.md`
- Evaluation CSV: `reports/eval_results.csv`
- Evaluation run log: `reports/run_log.txt`

## Current Snapshot

- 10 source PDFs are indexed for retrieval.
- The repo still runs without any LLM credentials by falling back to the local extractive answer path.
- The local runtime snapshot on 2026-04-02 uses an OpenAI-compatible backend via `.env` with model `gpt-5.4`.
- Bare gateway origins are now normalized to `/v1`, so the local LLM path no longer falls through to an HTML landing page.
- The demo supports FastAPI plus Streamlit, and both surfaces expose the configured answer backend in their runtime health state.

## Metrics From The Latest Local LLM Run

- answered: `18 / 20`
- refused: `2 / 20`
- errors: `0 / 20`
- citation rate: `90.00%`
- expected doc hit rate: `100.00%`
- answerability match rate: `100.00%`
- avg latency: `4907.60 ms`

## Validation Notes

- Live smoke for `LayoutLMv2新增的两个跨模态预训练任务是什么？` now returns a clean two-item list: `Text-Image Alignment (TIA)` and `Text-Image Matching (TIM)`.
- When the real LLM refuses a question despite strong retrieved evidence, PaperLens now falls back to the extractive rescue path instead of turning an answerable item into a false refusal.
- The retrieval backend is still `json`, not `FAISS`, and some comparison/table questions still depend on retrieval-noise mitigation rather than a stronger index backend.
- If this repo is moved to another machine, rerun `scripts/run_qa_smoke.py --require-llm --include-default-unanswerable` and `scripts/run_eval.py` after setting the local `.env`.
