# PaperLens

PaperLens is a local document QA demo built from the `.kiro` specs and the original planning READMEs in this repository. It turns the 10-paper PDF set under `data/raw_docs/` into a runnable retrieval + answer demo with FastAPI, Streamlit, citations, refusal handling, and a full 20-question evaluation runner.

## Current Status

- Demo UI screenshot: `screenshots/paperlens-demo-ui.png`
- Eval summary: `reports/eval_summary.md`
- Eval details: `reports/eval_results.csv`
- Eval run log: `reports/run_log.txt`
- Current metrics from the latest full run:
  - answered: `18 / 20`
  - refused: `2 / 20`
  - errors: `0 / 20`
  - citation rate: `90.00%`
  - expected doc hit rate: `100.00%`

## Project Layout

- `app/`: core runtime code
- `ui/`: Streamlit demo UI
- `scripts/`: build, smoke-test, and evaluation entry scripts
- `data/raw_docs/`: source PDFs
- `data/eval/questions.csv`: 20-question evaluation set
- `reports/`: generated manifests, summaries, and evaluation artifacts
- `screenshots/`: demo evidence images
- `.autonomous/paperlens-demo/`: long-running task state and handoff notes

## Environment

The repo is currently developed with the local virtual environment at `.venv`.
Use `.venv\Scripts\python` for all project commands on Windows.

Typical setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Optional extras for a richer runtime:

```powershell
.\.venv\Scripts\python -m pip install faiss-cpu opendataloader-pdf
```

## Build The Pipeline

1. Build the runtime manifest.

```powershell
.\.venv\Scripts\python scripts\build_manifest.py
```

2. Build the retrieval index.

```powershell
.\.venv\Scripts\python scripts\build_index.py
```

## Run QA Smoke Tests

```powershell
.\.venv\Scripts\python scripts\run_qa_smoke.py --include-default-unanswerable
```

## Run The API

```powershell
.\.venv\Scripts\python -m uvicorn app.api.main:app --reload
```

Available endpoints:

- `GET /health`
- `GET /documents`
- `POST /ask`

## Run The Streamlit Demo

```powershell
.\.venv\Scripts\python -m streamlit run ui/app.py
```

A demo-friendly autorun URL looks like this:

```text
http://127.0.0.1:8501/?question=LayoutLM%E5%9C%A8%E6%96%87%E6%A1%A3%E7%90%86%E8%A7%A3%E9%87%8C%E6%9C%80%E6%A0%B8%E5%BF%83%E7%9A%84%E5%BB%BA%E6%A8%A1%E5%AF%B9%E8%B1%A1%E6%98%AF%E4%BB%80%E4%B9%88%EF%BC%9F&autorun=1&mode=local&top_k=5
```

## Run The Full Evaluation

```powershell
.\.venv\Scripts\python scripts\run_eval.py
```

Outputs:

- `reports/eval_results.csv`
- `reports/eval_summary.md`
- `reports/run_log.txt`

## Git Sync

This repo includes a one-command GitHub sync helper for Windows:

```powershell
.\scripts\git_sync.ps1 -Message "feat: update demo"
```

Behavior:

- runs `pytest -q` by default if `.venv\Scripts\python.exe` exists
- stages all tracked and untracked changes with `git add -A`
- creates a commit with your message
- pushes the current branch to `origin`

Useful flags:

```powershell
.\scripts\git_sync.ps1 -Message "docs: update readme" -SkipTests
.\scripts\git_sync.ps1 -Message "wip: local snapshot" -NoPush
```

There is also a wrapper for double-click or `cmd.exe` usage:

```powershell
.\scripts\git_sync.cmd -Message "chore: sync repo"
```

Notes:

- the first push may still require GitHub authentication on this machine
- temporary browser profiles, `.autonomous/`, `.venv/`, and runtime index/chunk directories are ignored by `.gitignore`

## Known Limits

- The default `requirements.txt` intentionally keeps `faiss-cpu` and `opendataloader-pdf` optional because the current demo path can run without them.
- The current runtime still uses the JSON vector-store fallback because `.venv` does not yet include `faiss`.
- The answer service can run without LLM credentials, but the current fallback answer style is more extractive than a fully grounded generation model.
- Chunk quality task `T018` is still open, so some harder multi-part questions may still inherit chunk-level noise.

## Source Planning Docs

These original planning docs remain in the repo and are still the source-of-truth background for the implementation order:

- `PaperLens_README.md`
- `PaperLens_Linux_README.md`
- `PaperLens_OpenDataLoader_Integration.md`
- `.kiro/specs/paperlens/requirements.md`
- `.kiro/specs/paperlens/design.md`
- `.kiro/specs/paperlens/tasks.md`
