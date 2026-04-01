# Implementation Plan

本计划按照“先跑通，再增强”的顺序拆分。每个任务都应以 `paperlens/` 为项目根目录执行，避免一开始引入过多可选能力。默认优先完成 PDF-first 的稳定 MVP，再按任务尾部的扩展项升级。

## Phase 0: 项目骨架与共享约定

- [ ] T001 创建或补齐项目目录：`paperlens/app/`、`paperlens/ui/`、`paperlens/reports/`、`paperlens/tests/`。  
  依赖：无  
  完成标准：目录结构与 design 文档一致。

- [ ] T002 实现统一配置模块 `paperlens/app/core/config.py`，集中读取 `.env` 和默认值。  
  依赖：T001  
  完成标准：业务代码不再直接散读环境变量。

- [ ] T003 实现共享 schema 文件 `paperlens/app/models/schemas.py`，定义 `NormalizedDocument`、`ChunkRecord`、`AskResponse`、`EvalResult` 等模型。  
  依赖：T001  
  完成标准：所有核心中间产物都有明确数据结构。

- [ ] T004 添加最小 smoke test，验证配置加载和 schema 序列化。  
  依赖：T002、T003  
  完成标准：至少有 2 个测试文件可运行。

## Phase 1: 文档扫描与清单

- [ ] T005 实现 `manifest_service.py`，扫描 `paperlens/data/raw_docs/` 中的 PDF。  
  依赖：T002  
  完成标准：能识别当前 10 篇 PDF。

- [ ] T006 为清单记录补充文件大小、页数、哈希、状态字段。  
  依赖：T005  
  完成标准：同名或重复文件可被识别。

- [ ] T007 将清单结果写回 `paperlens/data/eval/doc_manifest.csv` 或新的 manifest 文件。  
  依赖：T006  
  完成标准：重复运行后文件内容可更新。

- [ ] T008 为扫描失败和损坏文件添加错误记录与日志输出。  
  依赖：T005  
  完成标准：错误不会导致整批扫描中断。

## Phase 2: PDF 解析适配层

- [ ] T009 定义解析器抽象 `parser_base.py`，统一 `parse(pdf_path)` 接口。  
  依赖：T003  
  完成标准：后续解析器都遵守同一输入输出约定。

- [ ] T010 实现默认解析器 `pdf_parser_pymupdf.py`。  
  依赖：T009  
  完成标准：至少能提取页码和页面文本。

- [ ] T011 实现可选增强解析器 `pdf_parser_opendataloader.py`，并通过配置切换。  
  依赖：T009  
  完成标准：增强解析器缺失时不阻塞全链路。

- [ ] T012 实现 `normalizer.py`，把不同解析器输出统一为 `NormalizedDocument`。  
  依赖：T010、T011  
  完成标准：统一保留 `doc_id`、`page_num`、`elements`、`bbox`、`section_path` 等关键字段。

- [ ] T013 将标准化 JSON 写入 `paperlens/data/parsed_docs/normalized/`。  
  依赖：T012  
  完成标准：每份 PDF 对应一个稳定输出文件。

- [ ] T014 为解析和标准化流程编写集成测试，至少验证 1 份 PDF。  
  依赖：T012、T013  
  完成标准：测试中能断言页码保留和输出文件存在。

## Phase 3: Chunk 构建

- [ ] T015 实现结构化 chunker `paperlens/app/rag/chunker.py`。  
  依赖：T003、T013  
  完成标准：优先按标题、段落、表格边界切块。

- [ ] T016 为 chunk 增加稳定 `chunk_id`、页码范围、章节标题和元素类型元数据。  
  依赖：T015  
  完成标准：任意一个 chunk 都能反查来源文档和页码。

- [ ] T017 把 chunk 输出到 `paperlens/data/chunks/`，建议采用 `jsonl`。  
  依赖：T016  
  完成标准：后续 embedding 模块可直接读取。

- [ ] T018 为超长内容、表格和跨页内容补充切分规则与单元测试。  
  依赖：T015、T016  
  完成标准：超长文本不会造成单个 chunk 失控。

## Phase 4: Embedding 与索引

- [ ] T019 实现 `embedder.py`，封装文本和查询的 embedding 调用。  
  依赖：T002、T017  
  完成标准：支持批量 embedding 与单条 query embedding。

- [ ] T020 实现 `index_store.py`，负责保存和加载 FAISS 索引及 chunk 元数据。  
  依赖：T019  
  完成标准：生成 `faiss.index` 与元数据文件。

- [ ] T021 编写索引构建命令或 CLI 入口，支持从 chunk 文件重建索引。  
  依赖：T020  
  完成标准：运行一次即可得到完整索引目录。

- [ ] T022 为“索引缺失”“配置缺失”“embedding 调用失败”添加显式报错。  
  依赖：T019、T020、T021  
  完成标准：异常状态对用户可见，不产生静默错误。

- [ ] T023 增加检索 smoke test，验证问题能返回 Top-K chunk。  
  依赖：T020、T021  
  完成标准：至少 1 个测试问题能跑通召回。

## Phase 5: 问答链路

- [ ] T024 实现 `retriever.py`，根据 query 向量执行 Top-K 检索。  
  依赖：T020  
  完成标准：返回 chunk 文本、分数、页码和文档名。

- [ ] T025 实现 `answer_service.py`，封装 grounded prompt 和模型调用。  
  依赖：T024  
  完成标准：答案必须依赖检索上下文生成。

- [ ] T026 实现引用映射逻辑，把命中 chunk 转换成文档名和页码引用。  
  依赖：T025  
  完成标准：每条答案都能附带结构化 citations。

- [ ] T027 实现低置信和无法回答分支。  
  依赖：T024、T025  
  完成标准：对无答案题目不输出伪造结论。

- [ ] T028 为问答服务添加单元测试和最小人工验证脚本。  
  依赖：T025、T026、T027  
  完成标准：至少验证 3 个问题，其中包含 1 个无法回答问题。

## Phase 6: API 与 UI

- [ ] T029 创建 FastAPI 入口 `paperlens/app/api/main.py`。  
  依赖：T003、T025  
  完成标准：服务可启动。

- [ ] T030 实现 `GET /health`、`GET /documents`、`POST /ask` 三个接口。  
  依赖：T029  
  完成标准：接口返回结构与 design 文档一致。

- [ ] T031 为 API 层补充请求参数校验和错误映射。  
  依赖：T030  
  完成标准：非法请求得到明确错误信息。

- [ ] T032 创建 Streamlit 页面 `paperlens/ui/app.py`。  
  依赖：T030  
  完成标准：可显示系统状态、问题输入、答案与引用。

- [ ] T033 在 UI 中展示“未构建索引”“无法回答”“引用列表”三种关键状态。  
  依赖：T032  
  完成标准：页面行为完整可演示。

- [ ] T034 完成一次本地端到端演示：启动 API、启动 UI、手工提问并截图。  
  依赖：T030、T032、T033  
  完成标准：至少得到一张可用于 README 的截图。

## Phase 7: 20 题评测

- [ ] T035 实现 `eval_service.py`，读取 `paperlens/data/eval/questions.csv`。  
  依赖：T025、T026、T027  
  完成标准：能逐题调用现有问答链路。

- [ ] T036 为每题保存回答文本、引用、耗时、命中文档和状态。  
  依赖：T035  
  完成标准：生成逐题结果文件。

- [ ] T037 计算汇总指标，包括回答率、拒答率、引用率、文档命中率和平均耗时。  
  依赖：T036  
  完成标准：生成汇总结果。

- [ ] T038 将评测结果写到 `paperlens/reports/eval_results.csv` 和 `paperlens/reports/eval_summary.md`。  
  依赖：T037  
  完成标准：结果可直接写进 README 或简历。

- [ ] T039 对 20 题完整跑批一次，检查失败题和异常题。  
  依赖：T038  
  完成标准：20 题全部有记录，即使部分失败也必须落表。

## Phase 8: 文档与收尾

- [ ] T040 更新项目 README，补充安装、索引构建、问答演示和评测命令。  
  依赖：T034、T039  
  完成标准：新读者能按 README 跑通项目。

- [ ] T041 整理演示素材，包括截图、评测摘要和项目亮点。  
  依赖：T034、T039  
  完成标准：能直接用于面试讲解。

- [ ] T042 做一次最终复查，重点检查配置项、目录路径、日志输出和失败处理。  
  依赖：T040、T041  
  完成标准：PaperLens 具备完整 MVP 交付质量。

## Execution Notes

1. 先完成默认解析器全链路，再接入增强解析器。
2. 先保证 API 和评测可跑，再去做 UI 细节优化。
3. 任何增强能力都不能破坏统一 schema 和引用链路。
4. 若实现过程中出现范围膨胀，优先保留以下四项：标准化解析、向量索引、带引用问答、20 题评测。
