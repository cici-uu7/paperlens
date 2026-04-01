# Requirements Document

## Introduction

PaperLens 是一个面向求职展示和端到端交付的多模态 PDF RAG 项目，项目根目录为 `paperlens/`。本期目标是在现有 10 篇公开 PDF 和标准版 20 题评测集的基础上，交付一套可运行的系统，完成以下闭环：

1. 扫描并校验 `paperlens/data/raw_docs/` 中的 PDF。
2. 将 PDF 解析为结构化中间结果，保留页码与版面相关元数据。
3. 生成可检索的 chunk、向量索引和文档清单。
4. 对用户问题执行向量检索并生成带引用的答案。
5. 通过 FastAPI 和 Streamlit 提供可演示的接口和界面。
6. 对 `paperlens/data/eval/questions.csv` 中的 20 个问题跑批评测并输出结果。

本期采用 “PDF-first，对多模态扩展友好” 的策略。也就是说，v1 必须做完 PDF 文本、标题层级、表格元数据、页码引用链路，但不把 OCR、扫描件增强、VLM、微调训练和复杂多代理编排列为首发阻塞项。

## In Scope

- 支持本地目录批量导入 PDF。
- 支持至少一种稳定 PDF 解析器，且保留解析器适配层。
- 支持统一的结构化文档 schema。
- 支持 chunk 生成、向量化、索引构建与查询。
- 支持问题回答、引用回溯和无法回答场景。
- 支持 API、简单 Web UI 和评测输出。
- 支持运行日志、配置文件和复现实验产物。

## Out of Scope

- 多租户权限系统。
- 在线文档上传后的异步队列系统。
- OCR-only 扫描件作为首发必做能力。
- 自训练 embedding 模型或微调生成模型。
- 复杂云原生部署、K8s、分布式索引。
- 强依赖浏览器插件或 SaaS 平台能力的实现方案。

## Requirements

### Requirement 1: 文档导入与校验

**User Story:** 作为项目开发者，我希望系统能从固定目录扫描和校验 PDF，这样我可以稳定地构建演示语料库并重复执行构建流程。

#### Acceptance Criteria

1. WHEN 用户执行导入或构建命令 THEN 系统 SHALL 扫描 `paperlens/data/raw_docs/` 下的 PDF 文件。
2. IF 文件不是 PDF、路径失效或文件损坏 THEN 系统 SHALL 跳过该文件并记录失败原因。
3. WHEN 系统发现同名或相同哈希的重复文档 THEN 系统 SHALL 默认避免重复导入，并在日志中标记重复来源。
4. WHEN 扫描完成 THEN 系统 SHALL 生成或更新文档清单，至少包含文件名、文档标题占位、页数、状态和错误信息字段。

### Requirement 2: PDF 解析与标准化

**User Story:** 作为项目开发者，我希望系统能把 PDF 解析成统一结构，这样后续 chunk、检索和引用模块就不依赖某一个具体解析器。

#### Acceptance Criteria

1. WHEN 系统解析一份 PDF THEN 系统 SHALL 至少保留页码、页面文本和文档级基本信息。
2. WHEN 解析器能够识别标题、段落、表格或列表 THEN 系统 SHALL 在标准化结果中保留元素类型。
3. IF 增强解析器不可用 THEN 系统 SHALL 回退到基础解析器，并继续输出合法的标准化 JSON。
4. WHEN 解析结果写盘 THEN 系统 SHALL 将标准化文档保存到 `paperlens/data/parsed_docs/normalized/`。

### Requirement 3: 结构化 chunk 生成

**User Story:** 作为检索系统开发者，我希望系统能基于结构化解析结果生成稳定 chunk，这样向量检索既能命中关键信息，也能把引用页码带回来。

#### Acceptance Criteria

1. WHEN 标准化文档可用 THEN 系统 SHALL 生成带稳定 `chunk_id` 的 chunk 数据。
2. WHEN 系统生成 chunk THEN 系统 SHALL 为每个 chunk 保留 `doc_name`、`page_start`、`page_end`、`section_title`、`element_types` 和原文内容。
3. IF 某一段内容超过配置阈值 THEN 系统 SHALL 按可配置规则拆分，并保留 overlap 或连续性信息。
4. WHEN chunk 生成完成 THEN 系统 SHALL 将结果保存为机器可读格式，供 embedding 和评测模块复用。

### Requirement 4: 向量索引构建

**User Story:** 作为项目使用者，我希望系统能把文档内容构造成可查询的向量索引，这样我提问时能快速召回相关内容。

#### Acceptance Criteria

1. WHEN 用户执行索引构建命令 THEN 系统 SHALL 对 chunk 执行 embedding 并建立向量索引。
2. WHEN 索引构建完成 THEN 系统 SHALL 将索引文件和索引元数据保存到 `paperlens/data/indexes/`。
3. IF embedding 调用失败或模型配置错误 THEN 系统 SHALL 显式报错并终止本次构建，而不是生成半成品索引。
4. WHEN 文档未变化且索引已存在 THEN 系统 SHALL 支持跳过重建或通过显式参数强制重建。

### Requirement 5: 问题检索与召回

**User Story:** 作为最终用户，我希望输入自然语言问题后系统能召回最相关的文档片段，这样答案有足够上下文支撑。

#### Acceptance Criteria

1. WHEN 用户提交问题 THEN 系统 SHALL 对问题向量化并从向量索引中返回 Top-K 候选 chunk。
2. WHEN 检索完成 THEN 系统 SHALL 保留 chunk 分数、chunk ID 和文档来源元数据，用于调试与评测。
3. IF 当前没有可用索引 THEN 系统 SHALL 返回明确的可执行提示，而不是空白结果。
4. IF 检索结果整体低于置信阈值 THEN 系统 SHALL 进入低置信或无法回答分支。

### Requirement 6: 带引用的答案生成

**User Story:** 作为演示用户，我希望系统给出的答案能标明来自哪份文档和哪一页，这样我能验证答案不是胡编的。

#### Acceptance Criteria

1. WHEN 检索到有效上下文 THEN 系统 SHALL 基于检索上下文生成答案，而不是脱离上下文自由发挥。
2. WHEN 答案包含事实性结论 THEN 系统 SHALL 附带至少一条文档级和页码级引用。
3. IF 检索上下文不足、相互冲突或无法支撑结论 THEN 系统 SHALL 明确说明“无法回答”或“不足以判断”。
4. WHEN 系统返回答案 THEN 系统 SHALL 同时返回答案文本、引用列表和最少一项调试元数据，例如命中 chunk 数量或总耗时。

### Requirement 7: API 服务能力

**User Story:** 作为前端页面或脚本调用方，我希望有稳定的后端接口，这样我能统一复用问答和文档状态能力。

#### Acceptance Criteria

1. WHEN 服务启动成功 THEN 系统 SHALL 提供健康检查接口。
2. WHEN 客户端请求文档清单 THEN 系统 SHALL 返回已扫描或已索引文档的基本状态。
3. WHEN 客户端提交问题 THEN 系统 SHALL 返回结构化响应，至少包含答案、引用和检索元数据。
4. IF 请求参数不合法 THEN 系统 SHALL 返回明确的校验错误信息。

### Requirement 8: 演示界面

**User Story:** 作为面试展示者，我希望有一个简单但完整的页面来演示提问、回答和引用展示，这样我可以直接给面试官演示系统能力。

#### Acceptance Criteria

1. WHEN 用户打开界面 THEN 系统 SHALL 展示项目标题、文档状态和提问入口。
2. WHEN 用户发起提问 THEN 系统 SHALL 在页面中展示答案、引用和核心命中文档信息。
3. IF 系统尚未构建索引 THEN 页面 SHALL 提示缺失步骤和下一步操作。
4. WHEN 系统返回无法回答 THEN 页面 SHALL 显示清晰的解释，而不是伪造答案或只返回空字符串。

### Requirement 9: 20 题评测

**User Story:** 作为项目开发者，我希望能用固定题集批量跑评测，这样项目结果可量化、可比较、可写入简历和 README。

#### Acceptance Criteria

1. WHEN 用户执行评测脚本 THEN 系统 SHALL 读取 `paperlens/data/eval/questions.csv` 中的 20 道题并逐题调用问答链路。
2. WHEN 评测完成 THEN 系统 SHALL 生成逐题结果文件和汇总文件，输出到 `paperlens/reports/`。
3. WHEN 问题带有标准答案或期望行为 THEN 系统 SHALL 至少计算回答可用性、引用命中情况、无法回答命中情况和耗时统计。
4. IF 某题执行失败 THEN 系统 SHALL 保留失败记录并继续处理其余题目。

### Requirement 10: 配置、日志与可复现性

**User Story:** 作为维护者，我希望关键配置和产物有统一规范，这样我能稳定复现 PaperLens 的构建和演示过程。

#### Acceptance Criteria

1. WHEN 系统读取模型、索引或阈值配置 THEN 系统 SHALL 统一从配置模块或环境变量加载。
2. WHEN 关键流水线执行 THEN 系统 SHALL 生成可阅读的日志，至少覆盖扫描、解析、索引、问答和评测。
3. WHEN 用户重复运行同一流程 THEN 系统 SHALL 在不修改输入的前提下产生可解释的一致结果或差异说明。
4. WHEN 新增解析器或替换 embedding 服务 THEN 系统 SHALL 尽量只影响适配层和配置层，而不破坏统一数据 schema。
