# PaperLens 从 0 到 1 教程

## 1. 先说清楚这个项目是什么

`PaperLens` 是一个多模态文档 RAG 项目。

它的目标不是做“普通聊天机器人”，而是做一个真正能：

1. 读文档
2. 找证据
3. 给出处
4. 回答问题

的系统。

你最终做出来的效果应该是这样的：

- 你把几篇论文 PDF、白皮书、技术报告放进系统
- 用户问一个问题
- 系统返回答案
- 同时告诉用户：这个答案来自哪份文档、哪一页、哪一段

这类项目很适合找工作，因为它能清楚体现：

- 文档解析
- chunk 设计
- 向量检索
- 关键词检索
- 混合召回
- 引用溯源
- 前后端联动
- 基础评测

---

## 2. 你现在最需要知道的现实边界

为了保证你能做完，这个教程故意分成两个版本：

### 第一版一定要做到的范围

第一版只要求你做到：

1. 支持 `PDF`
2. 支持导入 8 到 12 份文档
3. 支持问答
4. 支持显示引用页码和片段
5. 支持一个本地界面
6. 支持一份评测结果

### 第一版先不要做的内容

这些不是不能做，而是先不要做：

1. 不要先做 OCR
2. 不要先做图片理解
3. 不要先做 Docker
4. 不要先做云部署
5. 不要先做 DOCX / PPTX / XLSX 全格式支持
6. 不要先做复杂前端

### 为什么这样安排

因为你的目标不是“做一个无限扩展的平台”，而是先做出一个：

**稳定、可演示、可评测、能写进简历的作品集项目**

第一版只做 PDF，并不会让项目失色，反而会显著提高完成率。

等第一版做完后，再升级成真正的“多模态/多格式”版本。

---

## 3. 你最终要交付什么

这个项目完成后，你至少应该有下面这些东西：

1. 一套完整代码
2. 一份真正能看懂的 `README.md`
3. 8 到 12 份公开 PDF 数据
4. 一个可运行的 FastAPI 服务
5. 一个可运行的 Streamlit 页面
6. 一份评测 CSV
7. 一份评测结果 CSV
8. 一段 3 到 5 分钟演示视频
9. 一批截图

如果缺少其中一半，面试时会显得像半成品。

---

## 4. 你要准备什么

## 4.1 软件

你需要先准备：

1. Python 3.11
2. VS Code / Cursor / PyCharm 任意一个编辑器
3. PowerShell
4. 一个 OpenAI 兼容模型 API
5. 一个 embedding 模型 API 或本地 embedding 模型

### 检查 Python

打开 PowerShell，执行：

```powershell
python --version
```

你 ideally 应该看到：

```powershell
Python 3.11.x
```

如果你看到的是 3.9，也不是完全不行，但我建议你尽量换到 3.11。

---

## 4.2 数据

你需要准备 8 到 12 份公开 PDF。

### 推荐数据来源

你可以选这些：

1. arXiv 论文
2. 开源项目白皮书
3. 模型技术报告
4. benchmark 报告
5. 框架文档导出的 PDF

### 选择标准

文档最好满足这些条件：

1. 有页码
2. 有章节标题
3. 最好有表格
4. 你自己大概能读懂
5. 内容彼此有差异，方便做跨文档对比

### 第一版不建议的数据

先不要选：

1. 扫描件 PDF
2. 全是图片的 PDF
3. 过长的整本书
4. 完全不懂领域的文档

---

## 4.3 你要准备一个模型 API

你至少需要：

1. 一个生成模型
2. 一个 embedding 模型

如果你的服务商把两者都集成在一个平台里，也可以。

### 你需要确认的三件事

1. 你有 `API Key`
2. 你有 `Base URL`
3. 你知道模型名

---

## 5. 项目总路线图

这个教程按 7 个阶段走。

你必须按顺序做，不要跳步。

### 阶段 1：搭环境

目标：创建项目目录、虚拟环境、依赖安装成功

### 阶段 2：准备数据

目标：放入 PDF，写出评测问题

### 阶段 3：做文档解析

目标：把 PDF 变成结构化内容

### 阶段 4：做检索

目标：建立 chunk、embedding、索引、召回

### 阶段 5：做回答

目标：基于命中内容生成带引用答案

### 阶段 6：做接口和页面

目标：FastAPI + Streamlit 能跑通

### 阶段 7：做评测和包装

目标：拿出评测结果、截图、演示视频

---

## 6. 阶段 1：搭环境

## 步骤 1：创建项目文件夹

在你想保存项目的目录打开 PowerShell，执行：

```powershell
mkdir paperlens
cd paperlens
```

### 你应该看到什么

执行：

```powershell
pwd
```

应该显示你当前已经进入 `paperlens` 目录。

---

## 步骤 2：创建基础目录结构

继续执行：

```powershell
mkdir app,ui,data,scripts,reports,screenshots
mkdir app\rag,app\services
mkdir data\raw_docs,data\parsed_docs,data\chunks,data\indexes,data\eval
```

### 现在你的目录应该长这样

```text
paperlens/
  app/
    rag/
    services/
  ui/
  data/
    raw_docs/
    parsed_docs/
    chunks/
    indexes/
    eval/
  scripts/
  reports/
  screenshots/
```

---

## 步骤 3：创建虚拟环境

执行：

```powershell
python -m venv .venv
```

然后激活：

```powershell
.\.venv\Scripts\activate
```

### 你应该看到什么

命令行左边通常会出现：

```powershell
(.venv)
```

### 如果激活失败

先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

然后再执行激活命令。

---

## 步骤 4：创建依赖文件

在项目根目录创建 `requirements.txt`，内容完整复制下面这段：

```txt
fastapi
uvicorn
streamlit
python-dotenv
pydantic
pymupdf
sentence-transformers
faiss-cpu
rank-bm25
numpy
pandas
openai
tqdm
```

### 为什么第一版不用 Docling

因为你现在的目标是先稳稳做出 PDF 版本。

`PyMuPDF` 对 PDF 文本抽取更直接，第一版更容易跑通。

等你第一版成功后，再升级到 `Docling` 做更强的多格式解析。

---

## 步骤 5：安装依赖

执行：

```powershell
pip install -r requirements.txt
```

### 你应该看到什么

最后应该没有红色报错。

### 如果安装太慢

可以考虑加镜像源，但如果你本机网络没问题，先不折腾镜像。

---

## 步骤 6：检查关键依赖

执行：

```powershell
python -c "import fastapi,streamlit,fitz,faiss,numpy,pandas; print('ok')"
```

### 正常情况

输出：

```powershell
ok
```

### 如果失败

先不要继续下一步。

你应该先根据报错把依赖补齐，再继续。

---

## 步骤 7：创建基础文件

执行：

```powershell
ni .env -ItemType File
ni app\main.py -ItemType File
ni app\config.py -ItemType File
ni app\schemas.py -ItemType File
ni app\utils.py -ItemType File
ni app\rag\parser.py -ItemType File
ni app\rag\chunker.py -ItemType File
ni app\rag\embedder.py -ItemType File
ni app\rag\indexer.py -ItemType File
ni app\rag\retriever.py -ItemType File
ni app\rag\generator.py -ItemType File
ni app\services\ingest_service.py -ItemType File
ni app\services\qa_service.py -ItemType File
ni app\services\eval_service.py -ItemType File
ni ui\streamlit_app.py -ItemType File
ni scripts\run_eval.py -ItemType File
```

### 完成标准

这些文件都存在，不为空也没关系，后面再逐步写内容。

---

## 7. 阶段 2：准备数据

## 步骤 1：把 PDF 放入原始文档目录

把你准备好的 PDF 全部放进：

```text
data/raw_docs/
```

### 第一版推荐数量

先放 5 份，别一开始就放 12 份。

### 为什么

你现在做的是工程排错，不是堆数据。

先用 5 份跑通后，再加到 8 到 12 份。

---

## 步骤 2：先写评测题

在 `data/eval/` 下创建 `questions.csv`

表头如下：

```csv
question,gold_doc,gold_page_hint,gold_answer
```

### 第一批先写 10 个问题

建议分布：

1. 普通问答 5 个
2. 表格问题 2 个
3. 跨文档对比 2 个
4. 无法回答问题 1 个

### 示例

```csv
question,gold_doc,gold_page_hint,gold_answer
这篇论文的主要贡献是什么,paper1.pdf,3,提出了...
表2里表现最好的方法是什么,paper2.pdf,5,方法A
这两篇报告在推理成本上的观点有什么区别,report1.pdf|report2.pdf,4|6,...
```

### 这一步非常重要

如果你没有这份文件，后面很容易陷入：

“看起来好像能用，但不知道到底答得对不对”

---

## 8. 阶段 3：做最小配置

## 步骤 1：写 `.env`

把下面内容填进 `.env`

```env
OPENAI_API_KEY=你的key
OPENAI_BASE_URL=你的base_url
OPENAI_MODEL=你的生成模型名
EMBEDDING_MODEL=你的embedding模型名
```

---

## 步骤 2：写 `app/config.py`

把下面内容复制进去：

```python
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DOC_DIR = DATA_DIR / "raw_docs"
PARSED_DOC_DIR = DATA_DIR / "parsed_docs"
CHUNK_DIR = DATA_DIR / "chunks"
INDEX_DIR = DATA_DIR / "indexes"
EVAL_DIR = DATA_DIR / "eval"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
```

### 你为什么现在就写它

因为后面所有模块都要用到路径和 API 配置。

你如果现在不统一，后面文件之间会很乱。

---

## 步骤 3：写一个最小检查脚本

在 `app/utils.py` 里先放一个最简单的函数，例如路径检查和空目录创建。

你不需要一开始写很多逻辑，只要让它能：

1. 确保目录存在
2. 打印出配置是否读到

### 完成标准

你能在终端里测试配置文件被正确读取。

---

## 9. 阶段 4：先做文档解析

## 第一个核心目标

你现在不是在做问答，你是在做：

**把 PDF 安全地拆成可追踪文本**

如果这一步没做好，后面引用一定会乱。

---

## 步骤 1：实现 `app/rag/parser.py`

第一版建议只做 PDF 文本解析。

### 最低功能要求

它至少要做到：

1. 遍历 `data/raw_docs/`
2. 逐页读取 PDF
3. 抽取每页文本
4. 保存成结构化 JSON

### 每条记录至少要保留这些字段

1. `doc_name`
2. `page_num`
3. `text`
4. `source_path`

### 为什么先按页保存

因为页码是最简单、最稳定的引用单位。

第一版不要一上来就做很复杂的 block-level layout。

---

## 步骤 2：输出解析结果

每份 PDF 都输出成一个 JSON 文件，放到：

```text
data/parsed_docs/
```

### 命名建议

如果原文件叫：

```text
paper1.pdf
```

那么解析结果可以叫：

```text
paper1.json
```

---

## 步骤 3：先单独跑解析

不要和后面流程混在一起。

在 PowerShell 中手动运行解析逻辑，或者写一个临时脚本专门测试。

### 你要人工检查什么

随机打开 2 到 3 个解析后的 JSON，看：

1. 页码对不对
2. 文本有没有抽出来
3. 是否出现大量空字符串
4. 是否出现明显乱码

### 完成标准

至少 5 份 PDF 都能被解析出按页文本。

如果做不到，不要继续下一步。

---

## 10. 阶段 5：做 chunk

## 这一步的目标

把“按页文本”变成“适合检索的短片段”。

### 为什么不能直接整页检索

因为整页太长，容易：

1. 噪音太多
2. 召回不准
3. 上下文浪费

---

## 步骤 1：实现 `app/rag/chunker.py`

### 第一版 chunk 规则

你先用最简单稳定的规则：

1. 按页读取文本
2. 每 300 到 500 中文字或相当长度切一个 chunk
3. chunk 之间保留少量重叠

### 每个 chunk 至少保留

1. `chunk_id`
2. `doc_name`
3. `page_num`
4. `chunk_text`
5. `chunk_index`

### 这一步先别做什么

先别做：

1. 标题识别
2. 表格专门切分
3. 图像区域识别

这些都是第二版优化项。

---

## 步骤 2：保存 chunk 结果

把结果保存到：

```text
data/chunks/
```

### 完成标准

你能随便打开一个 chunk 文件，看见：

- 它来自哪份文档
- 它来自哪一页
- 它的内容是什么

---

## 11. 阶段 6：做 embedding 和索引

## 步骤 1：实现 `app/rag/embedder.py`

这一步的目标是：

把每个 chunk 转成向量。

### 最低要求

1. 读取所有 chunk
2. 调 embedding 模型
3. 保存向量结果

### 你现在不用纠结

先不要纠结 embedding 模型谁最好。

第一版只要能稳定生成向量就行。

---

## 步骤 2：实现 `app/rag/indexer.py`

### 你要建立两套索引

1. 向量索引：`FAISS`
2. 关键词索引：`BM25`

### 为什么两套都要做

因为：

- 向量检索适合语义相近
- BM25 适合关键词精确命中

混合用会比只用一种更稳。

### 输出位置

```text
data/indexes/
```

---

## 步骤 3：做一个最小索引测试

在 PowerShell 中写一个最小测试：

输入一个 query，看是否能返回 top-k chunk。

### 这时候你不需要生成最终答案

只要确认：

“输入 query 后，能找到几个看起来相关的 chunk”

就算这一步通过。

### 完成标准

对于你自己写的 3 个简单问题，至少 2 个能在前几条结果中看到正确文档片段。

---

## 12. 阶段 7：做检索器

## 你要写的文件

`app/rag/retriever.py`

## 检索流程建议

第一版按下面的固定流程写：

1. 接收用户问题
2. 做一个简单 query rewrite
3. 向量检索召回 top 10
4. BM25 检索召回 top 10
5. 合并结果
6. 去重
7. 取前 5 条

### 第一版可以先不做 rerank

如果你现在还没完全跑通，可以先不加 rerank。

先把“混合召回”跑通，后面再加 rerank。

### 完成标准

你能在终端中看到：

- 用户问题
- 命中的 5 个 chunk
- 每个 chunk 的文档名和页码

---

## 13. 阶段 8：做答案生成

## 你要写的文件

`app/rag/generator.py`

## 最低输出要求

模型返回时至少要有：

1. `answer`
2. `citations`

### 提示词必须包含这些要求

1. 只能根据上下文回答
2. 没有依据时明确说未找到依据
3. 不允许编造文档名和页码
4. 回答后附引用来源

### 第一版推荐输出格式

```json
{
  "answer": "......",
  "citations": [
    {
      "doc_name": "paper1.pdf",
      "page_num": 3,
      "snippet": "......"
    }
  ]
}
```

### 完成标准

至少 5 个简单问题能返回：

- 一段答案
- 至少 1 条引用

---

## 14. 阶段 9：做一键导入流程

## 你要写的文件

`app/services/ingest_service.py`

## 它要串起来的流程

1. 读取 `raw_docs`
2. 调 parser
3. 调 chunker
4. 调 embedder
5. 调 indexer

### 为什么要做成 service

因为后面你在 API 和页面里都要调用它。

### 完成标准

你可以通过一条命令完成整套导入。

---

## 15. 阶段 10：做问答服务

## 你要写的文件

`app/services/qa_service.py`

## 它要做的事

1. 接收用户问题
2. 调 retriever
3. 调 generator
4. 返回答案和引用

### 第一版不要做太多花活

先不要做：

1. 多轮对话记忆
2. 问题改写历史
3. 复杂对话上下文

第一版做单轮问答即可。

---

## 16. 阶段 11：做 FastAPI

## 你要写的文件

`app/main.py`

## 先只做 3 个接口

### `GET /health`

返回：

```json
{"status":"ok"}
```

### `POST /ingest`

触发导入流程。

### `POST /ask`

输入：

```json
{"question":"这篇论文的主要贡献是什么"}
```

输出：

```json
{
  "answer":"......",
  "citations":[...]
}
```

### 启动命令

```powershell
uvicorn app.main:app --reload --port 8000
```

### 验证方法

打开：

```text
http://127.0.0.1:8000/docs
```

### 完成标准

你能在 Swagger 页面调用 `/health`、`/ingest`、`/ask`。

---

## 17. 阶段 12：做页面

## 你要写的文件

`ui/streamlit_app.py`

## 第一版页面只做 3 块

### 区块 1：文档导入说明

告诉用户：

- 文档放哪里
- 什么时候点导入

### 区块 2：问题输入框

用户输入问题后，调用 `/ask`

### 区块 3：结果展示

显示：

1. 最终答案
2. 引用文档名
3. 引用页码
4. 原文片段

### 启动命令

```powershell
streamlit run ui/streamlit_app.py
```

### 完成标准

你能在网页里完成一次完整问答。

---

## 18. 阶段 13：第一轮手工验收

## 现在正式开始测

你先别写自动评测，先人工测。

### 测试题结构

1. 普通问答 5 个
2. 表格问题 2 个
3. 跨文档对比 2 个
4. 拒答问题 1 个

### 你要检查什么

1. 命中的文档是否正确
2. 页码是否大体正确
3. 答案是否大意正确
4. 不会答时是否拒答

### 完成标准

10 个问题里至少 7 个结果基本靠谱。

如果不到这个水平，不要急着录视频。

先继续调检索和提示词。

---

## 19. 阶段 14：自动评测

## 你要写的文件

`scripts/run_eval.py`

## 评测流程

1. 读取 `data/eval/questions.csv`
2. 逐题调用 `/ask`
3. 保存模型输出
4. 人工补充打分

### 推荐输出表头

```csv
question,pred_answer,pred_doc,pred_page,is_doc_correct,is_page_near,is_answer_ok,notes
```

### 输出位置

```text
reports/eval_result.csv
```

### 完成标准

你能拿出一张表来展示：

- 正确文档命中率
- 页码接近率
- 答案基本正确率

---

## 20. 阶段 15：项目包装

## 你必须做这几件事

### 1. 保存截图

至少保存：

1. 文档导入后页面
2. 普通问答示例
3. 表格问题示例
4. 跨文档对比示例
5. 引用展开示例
6. 评测结果表

### 2. 录视频

视频顺序建议：

1. 介绍项目
2. 展示文档列表
3. 问一个普通问题
4. 问一个表格问题
5. 展示引用和页码
6. 展示评测结果

### 3. 写根目录 README

你项目真正提交给别人看的 `README.md` 应该包含：

1. 项目简介
2. 技术栈
3. 目录结构
4. 安装步骤
5. 运行命令
6. 示例问题
7. 评测说明
8. 已知限制
9. 截图

---

## 21. 第一版什么时候算完成

只有满足下面这些条件，第一版才算完成：

1. 能导入 8 到 12 份 PDF
2. 能稳定回答问题
3. 能给出引用文档和页码
4. 能拒答
5. 有 FastAPI
6. 有 Streamlit 页面
7. 有评测结果
8. 有 README
9. 有演示视频

---

## 22. 常见坑和解决办法

## 坑 1：一开始就用太多文档

### 现象

不知道哪一步出问题。

### 解决

先用 3 到 5 份 PDF 跑通，再加量。

---

## 坑 2：整页文本太长，召回不准

### 解决

缩短 chunk 大小，控制在 300 到 500 字左右。

---

## 坑 3：模型乱编页码

### 解决

不要让模型自己生成页码。

页码应该来自你召回的 chunk metadata。

---

## 坑 4：没有先写评测题

### 解决

先写问题集，再开发。

---

## 坑 5：前端写太早

### 解决

先把 API 跑通，再写 Streamlit 页面。

---

## 23. 做完第一版后怎么升级

第一版完成后，你再做这些升级：

1. 加入 `Docling`
2. 支持 DOCX / PPTX / XLSX
3. 加入 OCR
4. 加入 rerank
5. 加入真正页面预览
6. 上云部署

但这些一定要在第一版完成之后再做。

---

## 24. 最后给你的执行建议

如果你现在真的要开始做，就严格按这个顺序：

1. 搭环境
2. 放 PDF
3. 写评测题
4. 做 parser
5. 做 chunk
6. 做 embedding + index
7. 做 retriever
8. 做 generator
9. 做 ingest_service
10. 做 qa_service
11. 做 FastAPI
12. 做 Streamlit
13. 做评测
14. 录视频

不要跳。

你只要按这个顺序推进，PaperLens 第一版是非常有希望做完的。
