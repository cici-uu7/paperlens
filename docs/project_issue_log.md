# 项目问题日志

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
