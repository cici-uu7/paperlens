# 项目问题日志

## 2026-04-02

### [mitigated][P2][resolved] 本轮改动完成后未立即走 skill 化收尾，现已补齐日志与同步
- Problem: 本轮虽然已经完成代码、测试和问题记录，但没有在同一收尾步骤里继续执行提交与推送，导致仓库一度停留在“已改完但未同步”的状态，也让用户看到“skill / 记录没有跟上”的体验断层。
- Root cause: 当前 Codex 的 skill 更像会话内工作流约束，不是文件变更后的自动监听器；这轮我先做完实现与验证，但没有把“日志、提交、推送”继续执行到最后一步。
- Action: 补记这条流程问题，并在同轮完成 `docs/project_issue_log.md` 更新、git 提交和推送，确保“改动、记录、同步”重新回到同一闭环。
- Validation: 本批改动会在本轮直接提交并推送到 `origin/main`；后续若再次出现只落代码不收尾的情况，应视为流程偏差而不是功能完成。

### [fixed][P1][resolved] 中文问题回答与引用卡片现支持“中文答案 + 题目信息 + 双语证据”
- Context: 用户反馈部分中文问题仍返回英文答案，引用列表只有 `doc_name / chunk_id / score`，很难快速看懂“这是哪份 PDF、哪篇资料、哪一页、这段英文到底是什么意思”。
- Root cause: `Citation` schema 只保留基础字段，`AnswerService` 也只做“尽量同语言回答”的软约束，没有对中文问题和英文证据做统一的本地化后处理。
- Fix: 扩展 `app/models/schemas.py` 中的 `Citation`，新增 `source_title / quote_original / quote_translation / quote_language`；在 `app/rag/answer_service.py` 中读取 runtime/eval manifest 的标题映射，对中文问题的英文答案做中文化兜底，并为英文证据自动补中文对照；在 `ui/streamlit_app.py` / `ui/app.py` 中把引用卡片改成 `PDF 文件名 / 资料题目 / 第几页 / score`，且英文证据按“英文在前、中文翻译在后”展示。
- Validation: `& .\.venv\Scripts\python.exe -m pytest tests/test_schemas.py tests/test_answer_service.py tests/test_ui_helpers.py -q` 通过 `24 passed`；同轮全量 `& .\.venv\Scripts\python.exe -m pytest -q` 通过 `49 passed`；真实 smoke 中 `LayoutLMv2新增的两个跨模态预训练任务是什么？` 现已输出 `1. 文本-图像对齐（TIA） / 2. 文本-图像匹配（TIM）`，且 citations 带 `source_title / page / score / 英文原文 / 中文对照`。
- Impact: 中文用户现在可以直接看懂答案和证据，不需要先猜 PDF 缩写或自行翻译英文证据；API / UI / eval 产物也都共享同一套更完整的 citation payload。

### [watch][P2][tracked] `RAG把哪两类记忆结合在一起？` 仍存在检索噪声，当前只是“显示更清楚”而不是“语义已完全收尾”
- Observation: 2026-04-02 新版真实 smoke 中，这个问题已经能输出中文答案，且 citations 也会带中英对照；但当前命中的仍可能是 `Decoding` / `Jeopardy question generation` 等错误 chunk，而不是“参数记忆 + 非参数记忆”的定义段。
- Risk: 这说明本轮已修好的主要是语言与引用可读性，而不是 F007 的检索噪声根因；若直接把所有短概念题都视为“已收尾”，后续展示时仍可能出现内容偏题。
- Follow-up: 把这个问题继续挂在 F007，后续优先检查短问句的 anchor term / citation rerank / focused retrieval 是否需要再收紧。

### [fixed][P2][resolved] 一键启动脚本现支持“复用现有 API，只补起缺失 UI”
- Problem: `scripts/start_demo.cmd` 遇到“8000 上已有 PaperLens API、8501 上还没有 UI”的半启动状态时，会直接因为单端口占用而退出，导致用户即使已经有可用 API，也必须手动关掉再重新一键启动。
- Action: 在 `scripts/start_demo.ps1` 中加入 PaperLens API 健康检查；若目标 API 端口已是可复用的 `/health` 服务，则直接复用现有 API，只新开 UI。同步更新 `scripts/stop_demo.ps1`，在这种复用场景下只停止本轮脚本自己管理的侧边进程。
- Validation: 2026-04-02 本地实际复现“8000 已有 API、8501 空闲”场景后，`cmd /c scripts\start_demo.cmd -NoBrowser -StartupTimeoutSeconds 15` 已能成功输出 “Reusing the existing API and starting only the UI.”，不再直接报端口冲突。
- Result: 一键启动脚本对本地演示的容错更强，不需要为了补起 UI 先手动停掉正在运行的 API。

### [fixed][P1][resolved] 裸网关地址现会自动补成 `/v1`，真实 LLM 不再误打到 HTML 首页
- Problem: 2026-04-02 实测本地 `.env` 中的 `OPENAI_BASE_URL=https://ice.v.ua` 会让 `chat.completions.create(...)` 返回整段网关 HTML 首页，而不是 JSON；代码随后静默退回 extractive fallback，导致表面上 `backend=openai`，实际并没有真正用上远端回答。
- Root cause: 现有配置层把网关地址原样传给 OpenAI SDK，没有处理“只填域名 / 根路径”的兼容网关常见写法；回答层也只按标准 completion 对象解析返回，没有显式识别 HTML 响应。
- Fix: 在 `app/core/config.py` 中把裸网关地址自动规范为 `/v1`；在 `app/rag/answer_service.py` 中兼容 raw-string 返回，并对 HTML 响应给出明确错误说明。
- Validation: `tests/test_config.py` 与 `tests/test_answer_service.py` 新增回归用例并通过；同日实测 `settings.openai_base_url` 已解析为 `https://ice.v.ua/v1`，`LayoutLMv2新增的两个跨模态预训练任务是什么？` 的真实 smoke 输出恢复为标准 `TIA / TIM` 两条列表。
- Impact: “本机已接入真实 LLM” 现在不再只是配置层假象，而是实际可用的运行状态；后续 smoke / eval 产物终于能真实代表远端回答路径。

### [fixed][P1][resolved] 真实 LLM 拒答时会回落到 extractive rescue，完整评测恢复到 18/20
- Problem: 修通真实 LLM 网关后，首轮完整 `run_eval.py` 从 `18 answered / 2 refused` 回落到 `14 answered / 6 refused`；回归集中在 Q05、Q08、Q10、Q12，模式都是检索里有证据，但 LLM 因措辞不够“直接”而拒答。
- Action: 在 `AnswerService.answer_question()` 中补上“LLM 拒答 -> extractive rescue”分支；只要 fallback 能基于已检索证据产出可靠答案，就不把该题直接判成最终 refused。
- Validation: 首轮真实 LLM eval 暂时掉到 `14 / 6 / 0`；补救逻辑后重新执行 `.\.venv\Scripts\python scripts\run_eval.py`，结果恢复为 `18 answered / 2 refused / 0 errors`，`citation_rate=90.00%`、`doc_hit_rate=100.00%`、`avg_latency_ms=4907.60`。
- Result: 当前系统已经具备“真实 LLM 优先、extractive rescue 兜底”的稳定运行方式，不会因为模型偶发保守就把整套评测显著拉低。

### [decision][P2][accepted] README / Demo 文案现在明确区分“仓库默认 fallback”与“本机真实 LLM 运行态”
- Decision: 更新 `README.md`、`.env.example`、`reports/demo_highlights.md` 和 `.autonomous` 跟踪文件，明确说明仓库默认仍支持无凭证 fallback，本地 `2026-04-02` 这台机器则已经接入 `gpt-5.4` 的 OpenAI-compatible 路径。
- Why: 如果继续混用“默认仓库能力”和“当前机器增强配置”，后续无论是做展示、做复盘还是排查回归，都很容易基于过期前提判断。
- Impact: F004-F006 已在本地任务清单中勾掉；接下来的优先级已经收敛到 F007 检索噪声、F008 FAISS、F009 同步收尾。

### [fixed][P2][resolved] 一键启动脚本已补齐配套的一键停止能力
- Action: 在 `start_demo.ps1` 中补充本地状态文件记录，并新增 `scripts/stop_demo.ps1` 与 `scripts/stop_demo.cmd`，优先停止一键启动脚本拉起的 API/UI 进程树，必要时再按端口识别目标进程。
- Validation: 停止脚本提供 `-DryRun`，可以先预览将要关闭的进程，不会直接影响当前正在运行的服务。
- Result: 现在 Windows 下的 PaperLens 演示具备完整的“启动/停止”配套脚本，不需要手动逐个关终端窗口。

### [fixed][P2][resolved] Windows 下新增 API + UI 一键启动脚本并支持 Chrome 自动打开
- Action: 新增 `scripts/start_demo.ps1` 与 `scripts/start_demo.cmd`，默认拉起 `uvicorn + streamlit`、轮询本地健康状态，并在可用时自动用 Chrome 打开 `?mode=api` 的演示页面。
- Extra: 同时给 `ui/streamlit_app.py` 补上 `api_base_url` query 参数支持，这样脚本在非默认端口下也能把页面自动指向正确的 API 地址。
- Validation: 启动脚本提供 `-DryRun` 便于本地检查命令与端口状态；`tests/test_ui_helpers.py` 已补充新 query 参数断言。
- Result: 本地演示不再需要手动开两个终端再复制 URL，Windows 下可以一条命令或双击脚本完成启动。

### [watch][P2][tracked] 当前机器已接入真实 LLM，但演示文档与评测说明仍沿用 fallback 前提
- Observation: 2026-04-02 在 `.venv` 中执行 `scripts/run_qa_smoke.py --include-default-unanswerable` 时，backend 已显示 `openai | configured=openai | model=gpt-5.4`；但 `reports/demo_highlights.md` 仍写着“mainly relies on the extractive fallback path”，部分 README / 日志 follow-up 也还以“若有真实 LLM 凭证”为前提。
- Risk: 当前仓库的 Demo 说明、评测解读和实际运行模式已经不完全一致，后续展示或继续优化时容易基于过期前提做判断。
- Validation: 同轮 `pytest -q` 通过 `43 passed`；`data/indexes/build_info.json` 显示当前索引后端仍为 `backend=json`，且 `.venv` 中 `faiss` / `opendataloader_pdf` 依旧不可用。
- Follow-up: 如果后续默认按真实 LLM 演示，应重新执行 smoke QA、完整 eval、必要的 UI 截图，并同步刷新 `reports/demo_highlights.md` 与 README 中关于 fallback 的描述；如果继续维持“无凭证也可运行”的仓库定位，则需要明确区分仓库默认能力与当前机器的增强配置。

### [watch][P2][tracked] 真实 LLM 已跑通，但列表题生成质量仍有收尾空间
- Observation: 同轮 smoke 中，`LayoutLMv2新增的两个跨模态预训练任务是什么？` 已命中正确论文与引用，但最终答案仍夹带英文原句，且第二条混入偏结果描述而非直接答案项。
- Risk: 这说明当前系统已经具备真实 LLM 主链路，但“列表题稳定输出清晰中文答案”仍未完全收尾；若直接作为最终 Demo 展示，体验会明显弱于检索与引用能力本身。
- Follow-up: 后续应优先针对真实 LLM 路径复测枚举题、检查 prompt / post-processing / citation rerank 的协同效果，并在刷新评测产物时把这类题单独纳入人工回看片单。

### [fixed][P1][resolved] Codex PowerShell 终端乱码与 conda 启动噪音已做用户级修复
- Problem: Codex 终端内文件字节正常，但普通 PowerShell 命令会被附加 `conda` 的 `UnicodeEncodeError` 和 `[y/N]` 残留，容易误判成文件编码损坏。
- Root cause: `C:\\Users\\dell\\Documents\\WindowsPowerShell\\profile.ps1` 中的 `conda init` 会在启动时触发 `activate base`；当前进程环境里又带着包含 `U+FFFD` 的坏 `PATH` 项，旧版 `conda 4.12.0` 用 `gbk` 输出时因此崩溃。
- Fix: 在用户级 PowerShell profile 前置 UTF-8 保护块，强制 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8` 和 PowerShell 输出编码为 UTF-8；同时把 `C:\\Users\\dell\\.condarc` 中的 `auto_activate_base` 设为 `false`。
- Validation: 2026-04-02 实测新 PowerShell 启动不再出现 `UnicodeEncodeError`；手动执行 `conda activate base` 正常；`Get-ChildItem G:\\` 可以正常输出中文目录名。
- Follow-up: 当前 Codex 进程如果本来就是从 `(base)` 环境里启动的，现有线程仍会继承该状态；彻底让新终端默认不进 `base` 需要重启 Codex 或从未激活 conda 的会话重新启动。

### [fixed][P1][resolved] 列表型问题的中文判定与 item-aware 补检索已接入回答链路
- Problem: `LayoutLMv2新增的两个跨模态预训练任务是什么？` 这类中文列表题没有稳定进入条目化回答链路，且 prompt 容易优先拿到 abstract / benchmark 概览块，而不是直接定义 `TIA` / `TIM` 的证据块。
- Action: 在 `app/rag/answer_service.py` 中补上稳定的中文计数与列表判定兜底；新增 item-aware 补检索，把 `question + focus_item` 与 `doc_hint + focus_item` 的结果并入候选池；同时提高带 acronym、定义句、official term 的 chunk 在 prompt/citation 排序中的权重。
- Validation: `tests/test_answer_service.py` 通过 `13 passed`，全量 `pytest` 通过 `43 passed`；真实索引下该问题的 prompt 前两块收敛到 `layoutlmv2_2012.14740_c0007` 与 `layoutlmv2_2012.14740_c0019`。
- Result: 列表题现在更容易输出明确的 numbered list，并把引用集中到真正定义答案项的 chunk，而不是泛介绍段落。

### [fixed][P2][resolved] 过程日志补记为“问题链”而不是只记最终结果
- Context: 本轮回看 `project_issue_log.md` 时，发现日志虽然记录了最终优化结果，但没有把影响实现判断的中间问题链写进去，后续复盘时会丢失排障依据。
- Symptom: 缺少“为什么一开始怀疑日志文件损坏”“为什么后来确认是终端显示问题”“为什么需要补技能约束和自动同步”这类过程性信息。
- Root cause: 现有日志习惯偏向记录收敛后的结论，导致探索阶段遇到的误判、工具噪音、流程缺口没有被同样当成 issue 记录。
- Fix: 本次补记同日过程问题，包括终端乱码误导、conda 激活噪音干扰、以及自动 commit/push 未即时执行的流程偏差；后续同类工作按“问题出现即记、结果收敛后补验证”的方式维护。
- Impact: 日志现在不仅能说明“改了什么”，也能说明“为什么这样改、期间踩过哪些坑”，更适合后续接手和长期任务续跑。

### [noted][P3][tracked] `project_issue_log.md` 文件字节编码正常，乱码来自终端显示
- Problem: 本轮更新日志时，PowerShell 中的中文显示成乱码，容易误判为日志文件本身已经损坏。
- Action: 用十六进制和原始字节检查 `docs/project_issue_log.md`，确认文件头为 UTF-8 BOM，正文中文字节内容正常。
- Result: 当前日志文件无需做编码抢救，只需要继续按 UTF-8 维护；如果终端仍显示乱码，应优先排查 PowerShell / conda 激活后的输出编码环境。

### [watch][P2][watch] conda 激活报错会污染命令输出并误导排障方向
- Observation: 本轮多次普通 `Get-Content`、`git status`、`git diff` 的命令输出后都被自动附加 conda `UnicodeEncodeError` 与 `[y/N]` 交互残留，终端信息噪声很高。
- Risk: 这类噪声容易把“文件内容乱码”和“终端显示乱码”混在一起，也会掩盖真正的 git 或测试输出，增加误判概率。
- Trigger: 任何经 PowerShell 启动并触发 conda shell hook 的命令。
- Follow-up: 后续遇到编码类问题时，优先用原始字节、十六进制或 `.venv\Scripts\python.exe` 做二次确认，不直接根据终端肉眼显示下结论。

### [mitigated][P2][tracked] 自动同步流程需要在编辑完成当轮立即执行
- Problem: 前一轮虽然已经有 `github-safe-sync` 工作流，但实际执行中仍出现“文件改了、日志也改了、却没有立刻提交和推送”的偏差，和预期的自动同步行为不一致。
- Action: 将本轮修复后的仓库改动纳入自动同步收尾，同时准备补强 `project-issue-log` skill，让“过程问题记录”与“编辑完成后自动同步”一起成为默认收尾动作。
- Follow-up: 本轮仓库内容补记完成后，直接执行安全同步脚本，让 `main` 不再停留在未提交状态。

### [fixed][P2][resolved] 选择性推送后恢复本地专属文件到当前工作树
- Problem: 旧版 `github-safe-sync` 在公开推送成功后会把 `main` 强制对齐到远程公开提交，导致 `docs/project_issue_log.md` 这类被过滤的本地专属文件从当前工作树消失，虽然它们已进入 `local/checkpoints`，但本地继续工作时会误以为文件没更新。
- Root cause: 同步脚本只实现了“本地 checkpoint + 远程筛选推送”，没有实现“推送完成后把排除文件恢复回当前工作树”这一步。
- Fix: 更新全局 `github-safe-sync` 脚本与说明，让被过滤的本地专属文件在 push 后自动从 `local/checkpoints` 恢复到当前工作树，并保持为本地未发布状态。
- Result: 公开项目内容仍然只推送到 GitHub，`project_issue_log.md` 等本地文件则会在当前仓库继续可见，后续不会再出现“日志已记录但当前分支看不到”的错觉。

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
