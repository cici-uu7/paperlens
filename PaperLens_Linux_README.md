# PaperLens Ubuntu / Linux 服务器教程

## 1. 这份文件是做什么的

这不是另一个新项目，而是 `PaperLens` 的 Linux 版操作手册。

你可以这样理解：

- [PaperLens_README.md](C:\Users\dell\Desktop\研二下\PaperLens_README.md)
  负责讲“项目逻辑怎么做”
- `PaperLens_Linux_README.md`
  负责讲“如果你租了 Ubuntu 服务器，应该怎么把这个项目在 Linux 上一步一步跑起来”

所以最推荐的使用方式是：

1. 先看 `PaperLens_README.md` 理解项目结构
2. 如果你决定在 Ubuntu 服务器上开发或部署，再严格按这份 Linux 指南执行

---

## 2. 这份指南适合什么场景

这份指南适合下面这些情况：

1. 你租了一台 Ubuntu 云服务器
2. 你想在 Linux 环境里学习大模型应用开发
3. 你想把 `PaperLens` 放到远程机器上运行
4. 你想从 Windows 本地切换到远程 Linux 开发

---

## 3. 你需要准备什么

## 3.1 服务器建议配置

第一版 `PaperLens` 对机器要求不算高。

### 最低建议

- 2 vCPU
- 4 GB 内存
- 40 GB 硬盘

### 更稳的建议

- 4 vCPU
- 8 GB 内存
- 60 GB 以上硬盘

### 操作系统建议

- Ubuntu 22.04 LTS
- 或 Ubuntu 24.04 LTS

### 为什么这样就够

因为第一版 `PaperLens` 主要做的是：

- PDF 解析
- embedding
- 索引
- 检索
- 调用远程模型 API

它不是在本机训练大模型，所以对 GPU 没有强依赖。

---

## 3.2 你还要准备这些东西

1. 一台能 SSH 登录的 Ubuntu 服务器
2. 一个有公网 IP 的主机
3. 一个 OpenAI 兼容模型 API
4. 一个 embedding 模型 API
5. 一批 PDF 文档

---

## 4. 整个 Linux 版流程是什么

你在 Ubuntu 服务器上的路线，建议严格按下面顺序做：

1. SSH 登录服务器
2. 更新系统
3. 安装 Python / Git / 基础工具
4. 创建项目目录
5. 创建虚拟环境
6. 上传或拉取项目代码
7. 配置 `.env`
8. 安装依赖
9. 放入 PDF
10. 运行 FastAPI
11. 运行 Streamlit
12. 打开端口并远程访问
13. 用 `tmux` 保持后台运行
14. 最后再考虑 `systemd` / `nginx`

不要跳步骤。

---

## 5. 第一步：SSH 登录服务器

在你本地电脑打开终端，执行：

```bash
ssh root@你的服务器IP
```

如果你的服务器不是 root 用户，就用：

```bash
ssh 用户名@你的服务器IP
```

### 第一次登录会发生什么

第一次会提示是否信任这台机器，输入：

```bash
yes
```

然后输入密码。

### 成功后的样子

你会看到类似：

```bash
root@ubuntu:~#
```

或：

```bash
yourname@ubuntu:~$
```

---

## 6. 第二步：更新系统

登录后先执行：

```bash
sudo apt update
sudo apt upgrade -y
```

### 为什么要先做这一步

因为很多 Python 依赖、证书、系统包都依赖系统状态。

如果这一步不做，后面更容易碰到奇怪问题。

---

## 7. 第三步：安装基础工具

执行：

```bash
sudo apt install -y python3 python3-venv python3-pip git curl unzip build-essential tmux
```

### 每个工具是干什么的

- `python3`：运行项目
- `python3-venv`：创建虚拟环境
- `python3-pip`：安装 Python 依赖
- `git`：拉代码
- `curl`：测试接口
- `build-essential`：编译一些依赖时会用到
- `tmux`：远程服务器上后台运行服务

---

## 8. 第四步：检查 Python 和 pip

执行：

```bash
python3 --version
pip3 --version
git --version
tmux -V
```

### 完成标准

这 4 条命令都能返回版本号。

如果有任何一条失败，不要继续下一步。

---

## 9. 第五步：创建项目目录

我建议你统一把项目放在：

```bash
~/projects/
```

执行：

```bash
mkdir -p ~/projects
cd ~/projects
mkdir paperlens
cd paperlens
```

### 现在你在哪里

执行：

```bash
pwd
```

你应该看到：

```bash
/home/你的用户名/projects/paperlens
```

---

## 10. 第六步：创建目录结构

执行：

```bash
mkdir -p app/rag app/services ui data/raw_docs data/parsed_docs data/chunks data/indexes data/eval scripts reports screenshots
touch README.md requirements.txt .env
touch app/main.py app/config.py app/schemas.py app/utils.py
touch app/rag/parser.py app/rag/chunker.py app/rag/embedder.py app/rag/indexer.py app/rag/retriever.py app/rag/generator.py
touch app/services/ingest_service.py app/services/qa_service.py app/services/eval_service.py
touch ui/streamlit_app.py scripts/run_eval.py
```

### 完成标准

执行：

```bash
find . -maxdepth 3 | sort
```

你能看到完整目录树。

---

## 11. 第七步：创建虚拟环境

执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 成功后

命令行前面通常会出现：

```bash
(.venv)
```

### 每次重新登录后都要做什么

以后你每次重新 SSH 登录服务器，进入项目目录后都要重新执行：

```bash
source .venv/bin/activate
```

---

## 12. 第八步：写 `requirements.txt`

用你熟悉的编辑器打开 `requirements.txt`。

如果你不会用 `vim`，最简单的方法是用 `nano`：

```bash
nano requirements.txt
```

把下面内容完整复制进去：

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

### 保存退出

如果你用的是 `nano`：

1. 按 `Ctrl + O`
2. 按回车保存
3. 按 `Ctrl + X` 退出

---

## 13. 第九步：安装 Python 依赖

执行：

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 完成标准

最后没有红色报错。

### 如果某个包安装失败

你先不要继续。

先把报错记下来，通常问题是：

1. 网络不通
2. Python 版本不对
3. 系统包缺失

---

## 14. 第十步：检查依赖

执行：

```bash
python -c "import fastapi,streamlit,fitz,faiss,numpy,pandas; print('ok')"
```

### 正常输出

```bash
ok
```

如果没有输出 `ok`，说明环境还没准备好。

---

## 15. 第十一步：配置 `.env`

执行：

```bash
nano .env
```

填入：

```env
OPENAI_API_KEY=你的key
OPENAI_BASE_URL=你的base_url
OPENAI_MODEL=你的生成模型名
EMBEDDING_MODEL=你的embedding模型名
```

### 为什么 Linux 上也要做这一步

因为服务器环境通常不会自动继承你本地的 key。

所有远程服务都要在服务器上单独配置。

---

## 16. 第十二步：写 `app/config.py`

把下面内容放进 `app/config.py`：

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

---

## 17. 第十三步：把 PDF 上传到服务器

你有两种方式。

### 方式 A：本地上传

在你本地电脑执行：

```bash
scp /本地路径/*.pdf 用户名@服务器IP:/home/用户名/projects/paperlens/data/raw_docs/
```

### 方式 B：服务器上直接下载

如果 PDF 本来就在网上，直接在服务器上下载到：

```bash
/home/用户名/projects/paperlens/data/raw_docs/
```

### 完成标准

回到服务器执行：

```bash
ls data/raw_docs
```

你能看到至少 5 个 PDF 文件。

---

## 18. 第十四步：把评测题也放好

在服务器上创建：

```bash
nano data/eval/questions.csv
```

表头如下：

```csv
question,gold_doc,gold_page_hint,gold_answer
```

### 第一批先写 10 个问题

建议和 Windows 版一样：

1. 普通问答 5 个
2. 表格问题 2 个
3. 跨文档对比 2 个
4. 拒答问题 1 个

---

## 19. 第十五步：先把项目逻辑代码补齐

到这里为止，Linux 环境已经搭好了。

接下来你要做的是：

严格按照 [PaperLens_README.md](C:\Users\dell\Desktop\研二下\PaperLens_README.md) 的逻辑部分，把这些文件逐步实现：

1. `app/rag/parser.py`
2. `app/rag/chunker.py`
3. `app/rag/embedder.py`
4. `app/rag/indexer.py`
5. `app/rag/retriever.py`
6. `app/rag/generator.py`
7. `app/services/ingest_service.py`
8. `app/services/qa_service.py`
9. `app/main.py`
10. `ui/streamlit_app.py`

### 这一段为什么我不重复写一遍

因为项目逻辑和 Windows 版是一样的。

Linux 版的重点不是改项目逻辑，而是：

- 让你在远程 Ubuntu 上知道每一步怎么执行
- 知道命令怎么跑
- 知道服务怎么暴露给外部访问

---

## 20. 第十六步：先做最小 FastAPI 测试

在 `app/main.py` 至少先写出：

1. `GET /health`
2. `POST /ingest`
3. `POST /ask`

### 启动命令

在项目根目录执行：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 为什么这里要用 `0.0.0.0`

如果你还是用默认的 `127.0.0.1`，外部机器无法访问。

远程服务器上要对外访问，就必须监听：

```bash
0.0.0.0
```

---

## 21. 第十七步：测试 FastAPI 是否活着

先在服务器本机测试：

```bash
curl http://127.0.0.1:8000/health
```

正常情况下应该返回：

```json
{"status":"ok"}
```

然后你再在浏览器打开：

```text
http://你的服务器IP:8000/docs
```

### 如果浏览器打不开

通常不是代码问题，而是：

1. 端口没开
2. 云服务器安全组没放行
3. 你启动时没用 `0.0.0.0`

---

## 22. 第十八步：运行 Streamlit

执行：

```bash
streamlit run ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

### 为什么也要指定 `0.0.0.0`

因为 Streamlit 默认只监听本机。

你如果希望从浏览器远程打开，就必须显式设置对外监听。

### 浏览器访问地址

```text
http://你的服务器IP:8501
```

---

## 23. 第十九步：放行端口

你至少需要确保这些端口对外可访问：

1. `8000`：FastAPI
2. `8501`：Streamlit

### 如果你用的是云服务器

去云平台控制台里放行：

- TCP 8000
- TCP 8501

### 如果服务器本机开了 UFW

执行：

```bash
sudo ufw allow 8000
sudo ufw allow 8501
sudo ufw status
```

---

## 24. 第二十步：用 `tmux` 保持服务后台运行

如果你直接在 SSH 窗口里启动服务，一旦你断开连接，服务通常就停了。

所以建议你一定学会 `tmux`。

## 启动 `tmux`

执行：

```bash
tmux new -s paperlens
```

### 在 `tmux` 里启动 FastAPI

```bash
cd ~/projects/paperlens
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 新建第二个 `tmux` 窗口

按：

```text
Ctrl + b
然后按 c
```

再启动 Streamlit：

```bash
cd ~/projects/paperlens
source .venv/bin/activate
streamlit run ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

### 退出但不关闭服务

按：

```text
Ctrl + b
然后按 d
```

### 以后重新进入

```bash
tmux attach -t paperlens
```

---

## 25. 第二十一步：第一轮远程验收

你现在要测试 4 件事：

1. `http://服务器IP:8000/docs` 能打开
2. `http://服务器IP:8501` 能打开
3. `/health` 返回正常
4. 页面能完成一次问答

### 只有这 4 条都通过

才说明 Linux 版最小服务跑通了。

---

## 26. 第二十二步：Linux 环境下的常见问题

## 问题 1：`python3 -m venv .venv` 失败

### 可能原因

没安装 `python3-venv`

### 解决

```bash
sudo apt install -y python3-venv
```

---

## 问题 2：`ModuleNotFoundError`

### 可能原因

你没激活虚拟环境。

### 解决

```bash
source .venv/bin/activate
```

然后重新运行命令。

---

## 问题 3：浏览器打不开接口

### 可能原因

1. 没监听 `0.0.0.0`
2. 端口没放行
3. 云安全组没开

### 解决顺序

1. 检查启动命令
2. 检查 UFW
3. 检查云控制台安全组

---

## 问题 4：SSH 断开后服务没了

### 原因

你没用 `tmux`

### 解决

把服务放到 `tmux` 里启动。

---

## 问题 5：embedding 很慢

### 原因

服务器 CPU 弱，或者 embedding 调用慢。

### 解决

第一版接受它慢一点，只要能跑通。

别因为追求速度而过早改太多架构。

---

## 27. 第二十三步：什么时候考虑更正式的 Linux 部署

只有当你已经满足下面这些条件，再考虑升级：

1. 项目逻辑完全跑通
2. 评测结果稳定
3. FastAPI 和 Streamlit 都能访问
4. 你已经录过演示视频

这时候你再考虑：

1. `systemd`
2. `nginx`
3. 域名
4. HTTPS
5. Docker

### 第一版先不要做这些

你现在的核心任务不是做 DevOps，而是做出可演示的项目。

---

## 28. 最后给你的 Linux 执行建议

如果你决定在 Ubuntu 上做 `PaperLens`，最稳的顺序就是：

1. 先搭 Linux 环境
2. 先让 FastAPI 和 Streamlit 能在服务器上打开
3. 再逐步补项目逻辑
4. 每做完一个模块就在服务器上测一次

不要等所有模块写完了才一起跑。

那样一旦出错，你会很难找原因。

---

## 29. 你现在应该怎么开始

如果你今天就开工，就按下面 10 条执行：

1. SSH 登录服务器
2. `apt update && apt upgrade`
3. 安装 Python / venv / git / tmux
4. 创建 `~/projects/paperlens`
5. 创建虚拟环境
6. 写 `requirements.txt`
7. 安装依赖
8. 写 `.env`
9. 上传 PDF
10. 开始按 `PaperLens_README.md` 补项目逻辑

做到这里，你就已经真正进入 Linux 开发路线了。
