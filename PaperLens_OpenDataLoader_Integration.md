# PaperLens 阶段 4 补充方案：使用 OpenDataLoader PDF 做文档解析

这份文件是对 `PaperLens_README.md` 中“阶段 4：先做文档解析”的增强版补充。

目的不是推翻原来的流程，而是：

1. 保持原有项目章节顺序不变
2. 只替换“PDF 解析/预处理层”
3. 让后面的 `chunk -> embedding -> index -> ask` 完全沿用原来的设计

你可以把它理解成：

- 原版阶段 4：基础 PDF 文本解析版
- 本补充版阶段 4：结构化 PDF 解析增强版

---

## 9. 阶段 4：先做文档解析

### 目标

这一阶段的目标仍然不变：

1. 把 `data/raw_docs/` 里的 PDF 解析成可供后续使用的结构化内容
2. 为后续 chunk、embedding、索引和问答准备稳定输入
3. 尽量保留页码、标题层级、表格、列表和阅读顺序
4. 为后面的 citation 和页码回溯留好 metadata

和原版不同的是，这次不再只做“按页抽纯文本”，而是引入 `OpenDataLoader PDF` 作为 PDF 解析器。

---

## 第一步：先明确这次替换的边界

这一步非常重要。

这次只替换下面这一层：

`PDF -> 解析结果`

不替换下面这些层：

- `chunker`
- `embedder`
- `indexer`
- `retriever`
- `generator`
- `qa_service`

也就是说，你原来的项目主链路仍然是：

`PDF -> parsed_docs -> chunks -> embeddings -> index -> retrieval -> answer`

只是 `parsed_docs` 的质量更高了。

---

## 第二步：为什么这里适合换成 OpenDataLoader PDF

原版简单解析方案的问题通常是：

1. 表格会被打散
2. 标题层级会丢失
3. 列表和阅读顺序容易乱
4. 引用页码能保留，但很难保留元素级坐标

`OpenDataLoader PDF` 更适合 `PaperLens` 的原因是：

1. 它能输出 `JSON / Markdown / HTML`
2. 它会重建文档布局，包括标题、列表、表格和阅读顺序
3. JSON 里保留 `page number` 和 `bounding box`
4. 输出天然适合后续做 `RAG / vector search / citation`
5. 默认带内容安全过滤，适合文档型 RAG 项目

所以对 `PaperLens` 来说，它最适合承担：

- PDF 解析器
- 结构化预处理器
- citation metadata 来源

---

## 第三步：这次阶段 4 的新目录约定

原项目里已经有：

```text
data/
  raw_docs/
  parsed_docs/
  chunks/
  indexes/
  eval/
```

现在继续沿用，不需要改大结构。

但是建议把 `parsed_docs/` 再细分成两层：

```text
data/
  raw_docs/
  parsed_docs/
    opendataloader_raw/
    normalized/
  chunks/
  indexes/
  eval/
```

其中：

- `opendataloader_raw/`
  直接存 OpenDataLoader 输出的原始文件
- `normalized/`
  存你自己项目统一格式的 JSON

这样做的原因是：

1. 第三方工具原始输出先保留，方便排错
2. 你项目内部只依赖统一格式，后面想切别的解析器也不会伤主链路

---

## 第四步：安装 OpenDataLoader PDF 所需环境

根据官方仓库，最关键的前置要求是：

1. `Java 11+`
2. `Python 3.9+`
3. `pip install opendataloader-pdf`

### Windows 下建议这样检查

```powershell
java -version
python --version
```

你需要看到：

- Java 至少 11
- Python 至少 3.9

### 安装命令

```powershell
pip install -U opendataloader-pdf
```

如果你在虚拟环境里，就先激活虚拟环境再装。

### 验证安装

```powershell
python -c "import opendataloader_pdf; print('ok')"
```

如果输出 `ok`，说明 Python 包可用。

---

## 第五步：先确定输出格式，不要一上来贪多

OpenDataLoader 支持很多输出格式，但对 `PaperLens` 第一版最推荐的组合是：

```text
json,markdown-with-html
```

原因如下：

### 为什么要 `json`

因为后面你需要：

1. 保留 `page number`
2. 保留 `bounding box`
3. 区分元素类型，例如 `heading / paragraph / table / list`
4. 给 citation 和调试留证据

### 为什么要 `markdown-with-html`

因为：

1. 普通段落和标题用 Markdown 很适合做 chunk
2. 遇到表格时，HTML 形式往往比纯 Markdown 更稳
3. 后面你如果做页面预览或调试，也更容易看结构

### 第一版不建议开太多格式

第一版先不要同时开：

- `pdf`
- `html`
- `markdown-with-images`

因为这些会让输出文件变多、调试更乱。

---

## 第六步：在项目里新增一个专门的解析器包装层

不要把第三方库直接写死在 `ingest_service.py` 里。

建议新增这个文件：

```text
app/services/pdf_parser_opendataloader.py
```

这个文件专门负责三件事：

1. 调用 `opendataloader_pdf.convert()`
2. 把原始输出写到 `data/parsed_docs/opendataloader_raw/`
3. 把输出再转换成你项目统一的 `normalized` JSON

这样，`ingest_service.py` 只需要“调用解析器”，不用关心第三方细节。

---

## 第七步：你自己的统一输出格式应该长什么样

这一步非常关键。

虽然 OpenDataLoader 已经能输出 JSON，但你项目内部不要直接依赖它的原始 JSON 结构。

建议你统一成下面这种格式：

```json
{
  "doc_name": "layoutlm_1912.13318.pdf",
  "doc_stem": "layoutlm_1912.13318",
  "parser": "opendataloader-pdf",
  "pages": [
    {
      "page_num": 1,
      "elements": [
        {
          "element_id": "p1_e1",
          "type": "heading",
          "level": "h1",
          "text": "LayoutLM: Pre-training of Text and Layout for Document Image Understanding",
          "bbox": [x1, y1, x2, y2]
        },
        {
          "element_id": "p1_e2",
          "type": "paragraph",
          "text": "....",
          "bbox": [x1, y1, x2, y2]
        }
      ]
    }
  ]
}
```

你内部统一后，后面的 chunker 才容易稳定工作。

至少保留这些字段：

1. `doc_name`
2. `page_num`
3. `element_id`
4. `type`
5. `text`
6. `bbox`
7. `level`
8. `parser`

---

## 第八步：`OpenDataLoader` 包装层建议的函数设计

在 `app/services/pdf_parser_opendataloader.py` 里，建议至少做这 3 个函数：

### 函数 1：批量解析 PDF

```python
def parse_pdfs_with_opendataloader(input_paths: list[str], output_dir: str) -> None:
    ...
```

职责：

1. 接收单个 PDF 或整个目录
2. 调用 `opendataloader_pdf.convert(...)`
3. 输出原始结果到 `opendataloader_raw/`

### 函数 2：把原始输出转成统一 JSON

```python
def normalize_opendataloader_output(raw_output_dir: str, normalized_dir: str) -> None:
    ...
```

职责：

1. 读取每份原始 JSON
2. 提取页面、元素类型、文本、页码、坐标
3. 转成你自己的统一格式

### 函数 3：给 ingest_service 调用的统一入口

```python
def parse_and_normalize(input_paths: list[str]) -> list[str]:
    ...
```

返回值建议是：

- 解析成功的 `normalized json` 文件路径列表

这样后面的 `ingest_service` 可以直接拿去喂 chunker。

---

## 第九步：推荐的调用参数

根据这个库的官方参数，`PaperLens` 第一版推荐这样用：

```python
import opendataloader_pdf

opendataloader_pdf.convert(
    input_path=["data/raw_docs/"],
    output_dir="data/parsed_docs/opendataloader_raw/",
    format="json,markdown-with-html",
    quiet=False,
    keep_line_breaks=False,
    use_struct_tree=False
)
```

### 这些参数为什么这么选

#### `format="json,markdown-with-html"`

这是主输出组合。

#### `quiet=False`

第一版开发时保留日志，排错更方便。

#### `keep_line_breaks=False`

默认先不要保留原始换行，避免 chunk 时被很多无意义换行干扰。

#### `use_struct_tree=False`

第一版先关掉，避免一开始引入额外复杂度。

如果后面发现某些 PDF 结构树质量很好，再单独测试打开。

---

## 第十步：专门说明几个不建议改的参数

### 不建议关闭内容安全

官方支持 `content_safety_off`，但对你的 RAG 项目，第一版不建议关闭。

原因：

1. 这是文档型 RAG 的安全加分项
2. 你后面做简历和 demo 时可以讲“预处理阶段做了 prompt injection 风险过滤”

### 不建议一篇 PDF 调一次 `convert()`

官方 README 明确提到它会启动 JVM。

所以建议：

1. 一次处理整个 `data/raw_docs/`
2. 或者一批处理多篇 PDF

不要在循环里每个文件单独起一次解析器。

---

## 第十一步：和原来的 `ingest_service.py` 怎么衔接

你原来的 `ingest_service.py` 逻辑大致是：

1. 读 `raw_docs`
2. 调 parser
3. 调 chunker
4. 调 embedder
5. 调 indexer

现在只要把第 2 步换成：

```text
调 pdf_parser_opendataloader.parse_and_normalize()
```

后面都不变。

新的逻辑变成：

1. 读 `raw_docs`
2. 调 `pdf_parser_opendataloader`
3. 读 `normalized` 结果
4. 调 `chunker`
5. 调 `embedder`
6. 调 `indexer`

---

## 第十二步：chunker 要做的最小兼容改造

如果你接了 OpenDataLoader，`chunker.py` 最少需要支持下面两种切块方式：

### 方式 1：按元素切块

适用于：

- 标题
- 段落
- 列表

做法：

1. 先按页面遍历
2. 再按元素顺序拼接
3. 每累计到目标长度就切一个 chunk

### 方式 2：表格单独成块

适用于：

- `type = table`
- 或带明显表格结构的 HTML/Markdown

做法：

1. 表格不要简单打散进普通段落
2. 一张表优先单独成一个 chunk
3. metadata 里保留：
   - `doc_name`
   - `page_num`
   - `element_type = table`
   - `source_element_ids`

这一步对你的“表格问题评测题”非常关键。

---

## 第十三步：citation 现在应该怎么设计

既然你已经有：

1. `page_num`
2. `bbox`
3. `element_id`

那每个 chunk 的 metadata 至少要保留：

```json
{
  "chunk_id": "...",
  "doc_name": "...",
  "page_num": 3,
  "element_type": "paragraph",
  "source_element_ids": ["p3_e4", "p3_e5"],
  "bbox_list": [
    [x1, y1, x2, y2],
    [x1, y1, x2, y2]
  ]
}
```

这样后面 `/ask` 返回答案时，你就可以输出：

1. 文档名
2. 页码
3. 命中片段
4. 如果前端以后升级，还能做元素高亮

---

## 第十四步：建议新增一个独立测试脚本

先不要一上来就走完整条 ingest 链。

建议新增：

```text
scripts/test_opendataloader_parse.py
```

这个脚本只做一件事：

1. 调 OpenDataLoader 解析 `data/raw_docs/`
2. 生成 `opendataloader_raw/`
3. 生成 `normalized/`
4. 打印每篇 PDF：
   - 页数
   - 元素数
   - heading 数
   - table 数

你先确认解析正确，再接 chunk。

---

## 第十五步：阶段 4 的手动执行顺序

这里按“小白一步一步执行”的方式写。

### 步骤 1：确认 Java 和 Python

```powershell
java -version
python --version
```

### 步骤 2：安装解析器

```powershell
pip install -U opendataloader-pdf
```

### 步骤 3：准备目录

确保存在：

```text
data/raw_docs/
data/parsed_docs/opendataloader_raw/
data/parsed_docs/normalized/
```

### 步骤 4：把 PDF 放到 `raw_docs`

例如：

```text
data/raw_docs/layoutlm_1912.13318.pdf
data/raw_docs/donut_2111.15664.pdf
```

### 步骤 5：单独运行解析脚本

你后面应当能做到类似：

```powershell
python scripts/test_opendataloader_parse.py
```

### 步骤 6：检查原始输出

你要看到：

```text
data/parsed_docs/opendataloader_raw/
```

下面出现每份 PDF 对应的：

- `.json`
- `.md`

### 步骤 7：检查统一输出

你要看到：

```text
data/parsed_docs/normalized/
```

下面出现每份 PDF 对应的统一 JSON。

### 步骤 8：人工抽查 2 到 3 篇 PDF

重点看：

1. 标题有没有被识别成 heading
2. 段落顺序是否正常
3. 表格有没有被保留下来
4. 页码是否正确
5. bbox 是否存在

---

## 第十六步：这一版阶段 4 的验收标准

到这里，阶段 4 算完成，至少要满足：

1. `data/raw_docs/` 下的 PDF 能批量解析
2. `opendataloader_raw/` 能产出原始 `json + md`
3. `normalized/` 能产出统一 JSON
4. 每个元素至少保留：
   - `type`
   - `text`
   - `page_num`
   - `bbox`
5. 至少 5 份 PDF 解析后结构基本正常
6. 至少 1 份含表格的 PDF 能识别出 table 相关元素
7. 后续 chunker 能直接读取 `normalized` 文件

如果这 7 条都满足，就可以进入下一阶段做 chunk。

---

## 第十七步：这个增强版对后续阶段有什么直接好处

### 对 chunk 阶段

更容易做：

1. 标题感知切块
2. 表格单独切块
3. 按元素顺序切块

### 对 retrieval 阶段

更容易做：

1. 表格题召回
2. 页码级引用
3. 多段来源合并

### 对 answer 阶段

更容易做：

1. citation
2. “答案来自第几页”
3. 后面升级到页面高亮

---

## 第十八步：这一版的推荐落地结论

如果你问“要不要把 OpenDataLoader PDF 接进 PaperLens”，我的建议是：

### 推荐接

因为它正好补的是你这个项目最薄弱的一层：

- 文档解析
- 表格保留
- 页码和坐标 metadata

### 但只接在阶段 4

不要把它扩散到整个系统设计里。

最稳妥的做法是：

1. 它只负责把 PDF 变成结构化结果
2. 你自己的项目只依赖统一格式 JSON
3. 后面 chunk、embedding、检索、问答继续按你原计划走

这样工程边界最清晰，也最适合面试时讲项目结构。

---

## 参考资料

- OpenDataLoader PDF 官方仓库：
  [https://github.com/opendataloader-project/opendataloader-pdf](https://github.com/opendataloader-project/opendataloader-pdf)
- OpenDataLoader Project 主页：
  [https://github.com/opendataloader-project](https://github.com/opendataloader-project)
