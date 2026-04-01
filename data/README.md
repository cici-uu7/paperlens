# PaperLens Demo Dataset

This folder is a ready-to-use starter dataset for the first `PaperLens` project.

Structure:

- `raw_docs/`: 10 public PDF papers downloaded from arXiv
- `eval/questions.csv`: machine-friendly QA pairs
- `eval/questions_answers_readable.md`: human-friendly QA list
- `eval/doc_manifest.csv`: paper metadata and why each paper was selected

Important notes:

- The PDFs are public arXiv papers and are intended here for personal learning and project demos.
- The QA pairs are handcrafted from paper abstracts, introductions, and well-known high-level contributions.
- This is a practical starter set for building and testing your retrieval pipeline. It is not an official benchmark.

Recommended usage:

1. Put all retrieval input on `data/raw_docs/`.
2. Use `data/eval/questions.csv` as your first-round evaluation set.
3. After you finish chunking and retrieval, run your system on these questions and compare outputs with `gold_answer`.

If you need to re-download the PDFs later, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\paperlens\scripts\download_demo_pdfs.ps1
```
