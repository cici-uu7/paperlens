# PaperLens Agent Guide

## 1. 沟通

- 默认使用中文；只有用户明确要求英文时再切换。
- 先读代码和文档，再下结论；不要凭印象猜测数据口径、阈值逻辑、回答链路、评估方式或当前运行模式。
- 说明尽量引用真实文件、真实命令、真实产物路径，例如 `README.md`、`docs/project_issue_log.md`、`reports/eval_summary.md`、`reports/eval_results.csv`、`reports/run_log.txt`、`scripts/start_demo.ps1`。
- 多步任务先用一句话说明“下一步要做什么”，再动手。
- 若用户提到“方案与计划”“验收材料”“对外口径”，默认联查 `.autonomous/paperlens-demo/`、`README.md`、`reports/` 与 `docs/`，不要只看单个脚本。

## 2. 项目事实

- 能力边界以现有代码、README、`docs/project_issue_log.md` 与 `.autonomous/paperlens-demo/` 为准；不要把未完成能力写成已完成。
- 这个仓库的项目根就是仓库根目录，不额外存在 `paperlens/` 子目录。
- 当前仓库同时支持：
  - 仓库默认 fallback 路径：无 LLM 凭证时可运行 Demo。
  - 当前机器的增强运行态：若本地 `.env` 已配置真实 LLM，则可走 OpenAI-compatible 路径。
- 写文档、日志、汇报时，要区分“仓库默认能力”和“当前机器实测结果”，不能混写。

## 3. 修改原则

- 优先做小而准的修改，不做无关重构，不为了“风格统一”大面积改写稳定代码。
- 路径、阈值、输出目录、字段名如果在多个文件重复出现，优先统一到已有模块或配置层，例如 `app/core/config.py`、schema、service 层，而不是散落在脚本里。
- 同类公共逻辑优先收口到已有模块，不要复制到 API、UI、脚本各写一份。
- 修改回答、引用、评测、启动脚本、文档口径时，要顺着调用链联查，不要只改表层展示。

## 4. 典型联查范围

遇到下面这些改动，默认至少联查这些文件或目录：

- 回答链路、引用字段、拒答逻辑：
  - `app/rag/answer_service.py`
  - `app/models/schemas.py`
  - `app/rag/retriever.py`
  - `app/api/main.py`
  - `ui/streamlit_app.py`
  - `tests/test_answer_service.py`
  - `tests/test_api.py`
  - `tests/test_ui_helpers.py`
- 配置、阈值、运行模式：
  - `app/core/config.py`
  - `.env.example`
  - `README.md`
  - 相关 tests
- 启动、停止、演示方式：
  - `scripts/start_demo.ps1`
  - `scripts/start_demo.cmd`
  - `scripts/stop_demo.ps1`
  - `scripts/stop_demo.cmd`
  - `ui/streamlit_app.py`
  - `README.md`
- 评测、产物、对外口径：
  - `scripts/run_eval.py`
  - `scripts/run_qa_smoke.py`
  - `reports/eval_summary.md`
  - `reports/eval_results.csv`
  - `reports/run_log.txt`
  - `reports/demo_highlights.md`
  - `README.md`
  - `.autonomous/paperlens-demo/`

## 5. 验证

- 完成修改后，至少做一种匹配验证：语法检查、定向 pytest、单脚本运行、关键路径 smoke test、隔离全流程验证。
- 不要空口声称“已可用”“效果提升”“已经修好”；要写明实际验证方式、命令、结果，以及未验证部分。
- 默认不要在当前项目目录随意生成测试产物；重验证优先使用已有脚本和既有产物路径，必要时用隔离工作区。
- 如果改动影响回答质量、引用展示、评测口径或启动流程，优先做最接近真实用户路径的 smoke test。

## 6. 文档与记录

- 变更运行命令、依赖、产物、目录结构、脚本行为时，同步更新 `README.md`。
- 发现 bug、回归、根因、流程偏差、重要取舍或后续风险时，在同一轮更新 `docs/project_issue_log.md`。
- 若改动影响后续续跑判断、当前阶段结论或 follow-up 优先级，同步更新 `.autonomous/paperlens-demo/` 相关文件。
- 若会影响计划书、验收材料或对外口径，要提醒并在需要时同步 `reports/` 和 `.autonomous` 中的对应内容。

## 7. 提交与推送闭环

对仓库内的真实改动任务，默认按以下闭环执行，除非用户明确要求停在中间：

1. 实现改动。
2. 做匹配验证。
3. 更新 `docs/project_issue_log.md`。
4. 需要时更新 `.autonomous/paperlens-demo/`。
5. 只暂存本次相关文件，不回退无关本地改动。
6. 提交。
7. 推送到 `origin/main`。

- 不要只改代码不收尾；也不要只口头说“后面再提交”。
- 如果提交或推送被阻塞，要明确说出阻塞点，而不是把任务停在半完成状态。

## 8. 不要做的事

- 不要把未完成能力写成已完成。
- 不要只改单个脚本而忽略相关 API、UI、tests、README、reports、日志口径。
- 不要把测试数据、临时脚本、缓存文件、无关产物当正式项目内容提交。
- 不要随意删除用户产物，尤其是 `reports/`、`screenshots/`、本地日志、手工整理的数据文件。
- 不要为了追求整洁而大范围重排已稳定代码。
