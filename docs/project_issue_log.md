# 项目问题日志

## 2026-04-01

### [decision][P2][accepted] Repo sync now uses a one-command local GitHub helper
- Decision: add `scripts/git_sync.ps1` and `scripts/git_sync.cmd` as the default repo sync path instead of relying on long manual `git add / commit / push` command chains.
- Why: this repo now mixes code, demo artifacts, screenshots, reports, and temporary browser/runtime files, so a consistent guarded sync flow is safer and easier to reuse.
- Impact: local sync can now run tests, stage changes, create a commit, and push to `origin` in one step; `.gitignore` was also tightened to exclude temp browser profiles and Streamlit logs.
- Next step: keep repo-level ignore rules current as new runtime artifacts appear, then use the helper for intentional sync points.

### [fixed][P1][resolved] Real Streamlit runtime no longer shadows the top-level `app/` package
- Problem: `streamlit run ui/app.py` failed in the real browser path with `No module named app.core`, recursion, and circular-import errors because `ui/app.py` shadowed the real `app/` package.
- Action: split the real implementation into `ui/streamlit_app.py`, kept `ui/app.py` as a thin launcher, removed `ui/` path shadowing, and validated the fix with a `runpy` shadow smoke test.
- Result: the Streamlit demo now loads correctly in a real browser window and the project has a stable screenshot artifact at `screenshots/paperlens-demo-ui.png`.

### [experiment][P1][noted] Full 20-question evaluation artifacts are now generated in `reports/`
- Setup: added `app/services/eval_service.py`, `scripts/run_eval.py`, and `tests/test_eval_service.py`, then ran the full eval set from `data/eval/questions.csv`.
- Result: the current run produced `reports/eval_results.csv`, `reports/eval_summary.md`, and `reports/run_log.txt` with `answered=18`, `refused=2`, `errors=0`, `citation_rate=90.00%`, `doc_hit_rate=100.00%`, and `answerability_match_rate=100.00%`.
- Conclusion: Phase 7 is now in place and the next high-value work is README/demo packaging rather than core evaluation plumbing.

### [experiment][P1][noted] Streamlit Demo 页面已可启动
- Setup: 在 `.venv` 中通过清华源安装 `streamlit 1.50.0`，新增 `ui/app.py`，并运行 `streamlit run ui/app.py --server.headless true --server.port 8501`。
- Result: 页面可以成功启动并输出 `Local URL: http://localhost:8501`；UI 已覆盖系统状态、文档清单、提问入口、拒答状态和引用列表。
- Conclusion: Phase 6 的页面层主干已经具备，本地 Demo 现在缺的主要是截图留档而不是页面本身。

### [decision][P2][accepted] Streamlit 页面默认支持 API 优先、失败回退本地服务
- Decision: `ui/app.py` 提供“自动 / 本地服务 / API”三种模式，默认优先调用 API，失败后回退到本地 `AnswerService`。
- Why: 当前项目既已有 FastAPI，又需要确保在 API 未单独启动时仍能展示 Demo，自动回退最适合现阶段的演示与排错。
- Impact: UI 不再被单一部署方式绑死，后续做截图或本地演示更灵活。
- Next step: 真正做 `T034` 时，优先用 API 模式演示；如果环境不稳，再用自动模式兜底。

### [watch][P2][watch] `.venv` 现已具备 numpy，但仍缺少 faiss
- Observation: 安装 Streamlit 后，`.venv` 中 `numpy` 已可导入，但 `faiss` 仍然缺失；当前 `data/indexes/build_info.json` 仍为 `backend=json`。
- Risk: 先前“缺 numpy”的判断已过期，如果下次续跑时沿用旧假设，可能做出错误排障；但因为依旧没有 `faiss`，索引后端并没有因此自动升级。
- Trigger: 后续再次重建索引或评估检索性能时。
- Follow-up: 如需切换到更接近原设计的检索路径，仍要单独补装 `faiss-cpu` 并重建索引。

### [experiment][P1][noted] AnswerService + FastAPI 最小闭环已跑通
- Setup: 新增 `app/rag/answer_service.py`、`scripts/run_qa_smoke.py`、`app/api/main.py`，并补上 `tests/test_answer_service.py`、`tests/test_api.py`。
- Result: `pytest` 当前 `21 passed`；`run_qa_smoke.py --include-default-unanswerable` 能跑出 2 个可回答问题和 1 个拒答问题；`TestClient(app)` 下 `/health`、`/documents`、`/ask` 均返回 200，且 `/ask` 会带结构化 citations。
- Conclusion: PaperLens 已从“只有索引与检索”推进到“最小问答 API 可调用”的阶段。

### [decision][P2][accepted] 回答层内部 over-fetch 并过滤版面噪声
- Decision: `AnswerService` 在调用 `Retriever` 后，内部扩大候选数量，并在句子级过滤 `+ + +` 等明显排版噪声，再做 citation 选择。
- Why: `LayoutLM` 问题的初始 Top 5 虽然命中了正确论文，但前几条 chunk 多为版面噪声，不适合直接拼成回答。
- Impact: 当前无需先重写 chunker，也能让 Phase 5 和 API 主链路继续向前推进。
- Next step: 后续仍应回到 `T018` 解决根因，而不是长期依赖回答层补救。

### [watch][P2][watch] 无 LLM 凭证时的 extractive fallback 仍不适合精确多项枚举题
- Observation: 在无 `OPENAI_API_KEY/LLM_MODEL` 的情况下，`AnswerService` 会退回到抽取证据句的 fallback。该路径能保持可解释和可拒答，但对 `LayoutLMv2新增的两个跨模态预训练任务是什么？` 这类需要精确列举多项答案的问题仍偏弱。
- Risk: 如果直接拿当前 fallback 做最终 Demo，用户会感受到“能定位论文，但回答还不够像成熟助理”。
- Trigger: 提问需要准确列举多个点、跨句整合或中文自然化表达时。
- Follow-up: 条件允许时尽快接入真实 LLM，并在 UI 中展示“证据+答案”而不是只强调最终文案质量。

### [watch][P2][watch] 当前检索后端仍是 JSON，不是 FAISS
- Observation: 2026-04-01 在 `.venv` 中重新执行 `scripts/build_index.py` 后，`data/indexes/build_info.json` 显示 `backend=json`、`vector_dim=1024`、`chunk_count=1275`。
- Risk: 当前检索路径仍依赖 JSON 向量存储，性能和可扩展性都弱于原始设计中的 `FAISS`。
- Trigger: 在更大语料、更多 chunk 或 API/UI 并发场景下，会更明显地暴露出来。
- Follow-up: 后续优先补齐 `numpy/faiss-cpu` 或切换到真实 embedding 环境，再重建索引。

### [decision][P2][accepted] 回退 embedding 升级为 mixed-language hashing-1024 + metadata rerank
- Decision: 在未配置真实 embedding 服务、且 `.venv` 中缺少 `faiss/numpy` 的前提下，先把回退方案升级为 `hashing-1024`，并加入 mixed-language tokenization、`doc_name/section_title` 检索锚点、candidate over-fetch 与 metadata bonus。
- Why: 原始 `hashing-256` 对中文问题召回英文论文时 hash collision 和版本名串扰过重，无法支撑后续 Demo 推进。
- Impact: 当前 fallback 对模型名类问题明显更稳，已足够支撑继续实现 `retriever.py`、`answer_service.py` 和 API/UI 主链路。
- Next step: 在进入评测和最终 Demo 前，尽量切回真实 embedding 或更强的本地模型。

### [experiment][P1][noted] Index + Retriever 主干已跑通
- Setup: 新增 `app/rag/errors.py`、`app/rag/retriever.py`，扩展 `embedder.py`、`index_store.py`、`scripts/build_index.py`，并在 `.venv` 中运行 `pytest` 和真实检索 smoke。
- Result: `pytest` 当前 `14 passed`；`data/indexes/` 已生成 `build_info.json`、`chunk_metadata.jsonl`、`vector_store.json`；问题 `LayoutLM在文档理解里最核心的建模对象是什么？` 的 Top 5 结果已全部来自 `layoutlm_1912.13318.pdf`，`Self-RAG为什么比固定检索式RAG更灵活？` 的 Top 3 也都命中 `self_rag_2310.11511.pdf`。
- Conclusion: Phase 4 到 T024 的主干能力已经具备，当前关键阻塞从“索引构建”转移到“回答生成、引用映射和拒答策略”。

### [watch][P2][watch] 泛化问题上的回退检索仍有语义重叠噪声
- Observation: 真实 smoke 中，问题 `RAG把哪两类记忆结合在一起？` 的 Top 3 结果会同时包含 `self_rag_2310.11511.pdf` 与 `rag_2005.11401.pdf`，且 `Self-RAG` 可能排在 `RAG` 之前。
- Risk: 若直接进入问答生成，可能把近邻文档中的相似概念混写进答案，影响引用准确性。
- Trigger: 当问题本身较短、语义重叠高，且依赖 hashing fallback 而非真实 embedding 时。
- Follow-up: 在 `answer_service.py` 中增加更严格的引用约束与低置信分支，并在条件允许时切换到真实 embedding。

## 2026-03-31

### [watch][P2][watch] 首轮 chunk 粒度偏细
- Observation: 默认 PyMuPDF + block 级标准化后，10 份文档在 `data/chunks/` 中共产生 `1275` 个 chunk。
- Risk: 召回噪声会变高，后续 embedding/index 成本也会明显上升。
- Trigger: 当进入 Phase 4 构建索引和检索评测时，会直接放大当前切块质量问题。
- Follow-up: 优先执行 `T018`，改进标题识别、作者区块处理和过细切分规则。

### [experiment][P2][noted] `.venv` parser 与正式路径写盘已跑通
- Setup: 在 `.venv` 中补齐关键依赖后，实现 parser/normalizer/chunker，并通过提权写入 `data/parsed_docs/normalized/` 与 `data/chunks/`。
- Result: `reports/doc_manifest_runtime.csv` 状态全部为 `ready`；`data/parsed_docs/normalized/` 生成 10 个 JSON；`data/chunks/` 生成 10 个 JSONL，共 1275 个 chunk。
- Conclusion: PaperLens 已经从“只有计划”进入“默认 PDF-first 数据流水线可落盘”的阶段。

### [experiment][P2][noted] `.venv` parser baseline已跑通真实 PDF
- Setup: 在 `.venv` 中补齐 `pydantic`、`fastapi`、`pymupdf`、`uvicorn`、`openai`、`pytest`、`python-dotenv` 后，实现 `parser_base.py`、`pdf_parser_pymupdf.py`、`normalizer.py`，并对 `layoutlm_1912.13318.pdf` 执行真实解析。
- Result: `.venv` 下 `pytest` 共通过 6 项测试，生成 `reports/normalized_preview/layoutlm_1912.13318.json`，摘要为 `page_count=9`、`element_count=174`。
- Conclusion: Phase 2 的默认 parser 主干已经可用，当前主要阻塞转为 `data/` 写盘权限与 OpenDataLoader 增强解析器接入。

### [experiment][P2][noted] 基础骨架与 manifest 初始化验证通过
- Setup: 新增配置模块、schema 模块、manifest service、manifest builder 和 3 组基础测试后，执行 `python -m pytest -q` 与 `python scripts/build_manifest.py`。
- Result: `pytest` 通过 5 项测试，并成功生成 `reports/doc_manifest_runtime.csv`；10 篇 PDF 全部被识别，但因缺少 `PyMuPDF` 均标记为 `pending_pdf_runtime`。
- Conclusion: Phase 0 和 Phase 1 的“骨架 + 扫描”已可续跑，当前主阻塞转为依赖安装与 parser 实现。

### [decision][P2][accepted] 以仓库根目录作为 PaperLens 项目根
- Decision: 不额外创建 `paperlens/` 子目录，直接把 `G:\python_code\paperlens` 视为 `.kiro` 和 README 里的项目根。
- Why: 当前仓库已经在根目录提供了 `data/`、`scripts/` 和所有原始规划文档，再嵌套一层只会让路径偏离原始计划。
- Impact: 后续代码统一落在根目录下的 `app/`、`ui/`、`reports/`、`tests/`。
- Next step: 在 `.autonomous/paperlens-demo/task_list.md` 里长期固定这条路径映射。

### [P2][fixed] UTF-8 文档读取乱码
- Problem: PowerShell 默认编码把 `.kiro/specs/paperlens/*.md` 和根目录 README 读成乱码，无法可靠提取原始计划。
- Action: 统一改用 `Get-Content -Encoding UTF8` 读取技能文件、规格文档和 README。
- Result: `.kiro` 的 requirements/design/tasks 与 3 份原始 README 已全部恢复可读，可用于建立长期任务清单。

### [watch][P2][watch] 当前环境缺少运行期核心依赖
- Observation: 2026-03-31 初始检查结果显示 `pydantic`、`fastapi`、`fitz` 未安装，只有 `pytest` 和 `dotenv` 已可用；该问题已通过 `.venv` 分批安装得到缓解，但系统 Python 仍旧缺依赖。
- Risk: 如果误用系统 Python 执行 parser/API 流程，仍会得到 `ModuleNotFoundError` 或错误的 manifest 状态。
- Trigger: 使用 `python` 而不是 `.venv\Scripts\python` 执行新代码时。
- Follow-up: 后续开发默认使用 `.venv`；最终 README 里需要明确这一点。

### [watch][P2][watch] 当前沙箱在 `data/` 下新建子目录被拒绝
- Observation: 2026-03-31 使用 `New-Item` 创建 `data/parsed_docs`、`data/chunks`、`data/indexes` 返回 `UnauthorizedAccessException`，但根目录下的新包目录可正常创建。
- Risk: 后续 parser、chunk 和 index 的最终写盘路径需要二次验证，短期内更适合先把生成类产物放在 `reports/` 或临时目录。
- Trigger: 当首次把运行时产物写入 `data/` 新子目录时会再次触发。
- Follow-up: 当前已通过按需提权完成目录与文件写入，后续需要把这条能力整理成更稳定的开发流程。
