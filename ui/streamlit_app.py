"""Streamlit UI implementation for the PaperLens demo."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd
import requests
import streamlit as st


UI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[1]
filtered_sys_path = []
for entry in sys.path:
    try:
        resolved_entry = Path(entry or ".").resolve()
    except OSError:
        filtered_sys_path.append(entry)
        continue
    if resolved_entry != UI_DIR:
        filtered_sys_path.append(entry)
sys.path[:] = filtered_sys_path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings, get_settings
from app.rag import AnswerService, IndexNotBuiltError, PaperLensRagError
from app.services.manifest_service import scan_raw_docs


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
UI_MODE_AUTO = "自动"
UI_MODE_LOCAL = "本地服务"
UI_MODE_API = "API"


def _escape_multiline_text(value: Any) -> str:
    return html.escape(str(value or "")).replace("\n", "<br/>")


def _normalize_query_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        return str(value[0] or "")
    return str(value or "")


def load_example_questions(settings: Settings, limit: int = 6) -> List[str]:
    questions_path = settings.eval_dir / "questions.csv"
    if not questions_path.exists():
        return []

    questions: List[str] = []
    with questions_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            question = (row.get("question") or "").strip()
            if question:
                questions.append(question)
            if len(questions) >= limit:
                break
    return questions


def load_local_build_info(settings: Settings) -> Dict[str, Any]:
    build_info_path = settings.index_dir / "build_info.json"
    if not build_info_path.exists():
        return {}
    return json.loads(build_info_path.read_text(encoding="utf-8"))


def load_local_indexed_doc_names(settings: Settings) -> set[str]:
    metadata_path = settings.index_dir / "chunk_metadata.jsonl"
    if not metadata_path.exists():
        return set()

    names: set[str] = set()
    with metadata_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            doc_name = payload.get("doc_name")
            if doc_name:
                names.add(str(doc_name))
    return names


def load_local_documents(settings: Settings) -> List[Dict[str, Any]]:
    runtime_manifest = settings.reports_dir / "doc_manifest_runtime.csv"
    if runtime_manifest.exists():
        with runtime_manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        rows = [record.to_row() for record in scan_raw_docs(settings)]

    indexed_names = load_local_indexed_doc_names(settings)
    documents: List[Dict[str, Any]] = []
    for row in rows:
        filename = row.get("filename", "")
        documents.append(
            {
                "doc_name": filename,
                "title": row.get("title", ""),
                "page_count": int(row["page_count"]) if row.get("page_count") else None,
                "status": row.get("status", ""),
                "indexed": filename in indexed_names,
            }
        )
    return documents


def build_local_snapshot(settings: Settings) -> Dict[str, Any]:
    build_info = load_local_build_info(settings)
    documents = load_local_documents(settings)
    indexed_count = sum(1 for doc in documents if doc["indexed"])
    answer_backend = AnswerService.describe_backend(settings)
    return {
        "source": "local",
        "health": {
            "status": "ok",
            "index_built": bool(build_info),
            "raw_docs_dir": str(settings.raw_docs_dir),
            "answer_backend": answer_backend,
        },
        "documents": {"count": len(documents), "documents": documents},
        "build_info": build_info,
        "indexed_count": indexed_count,
    }


def fetch_api_json(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + path
    timeout = 12
    if method.upper() == "GET":
        response = requests.get(url, timeout=timeout)
    else:
        response = requests.post(url, json=payload or {}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def build_runtime_snapshot(
    mode: str,
    settings: Settings,
    api_base_url: str,
) -> Tuple[Dict[str, Any], Optional[str]]:
    build_info = load_local_build_info(settings)
    if mode in {UI_MODE_AUTO, UI_MODE_API}:
        try:
            health = fetch_api_json(api_base_url, "/health")
            documents = fetch_api_json(api_base_url, "/documents")
            return (
                {
                    "source": "api",
                    "health": health,
                    "documents": documents,
                    "build_info": build_info,
                    "indexed_count": sum(
                        1 for doc in documents.get("documents", []) if doc.get("indexed")
                    ),
                },
                None,
            )
        except Exception as exc:
            if mode == UI_MODE_API:
                raise
            return build_local_snapshot(settings), f"API 不可用，已自动回退到本地服务：{exc}"
    return build_local_snapshot(settings), None


def ask_question(
    mode: str,
    settings: Settings,
    api_base_url: str,
    question: str,
    top_k: int,
) -> Tuple[Dict[str, Any], str]:
    if mode in {UI_MODE_AUTO, UI_MODE_API}:
        try:
            return (
                fetch_api_json(
                    api_base_url,
                    "/ask",
                    method="POST",
                    payload={"question": question, "top_k": top_k},
                ),
                "api",
            )
        except Exception:
            if mode == UI_MODE_API:
                raise
    service = AnswerService.from_settings(settings)
    return service.answer_question(question, top_k=top_k).to_dict(), "local"


def format_failure_message(response_payload: Dict[str, Any]) -> str:
    reason = response_payload.get("failure_reason") or "unknown"
    mapping = {
        "insufficient_context": "检索到的上下文不足，系统选择拒答。",
        "low_confidence": "证据相关性过弱，系统选择拒答。",
    }
    return mapping.get(reason, f"当前回答失败，原因：{reason}")


def parse_demo_query_params(params: Mapping[str, Any]) -> Dict[str, Any]:
    question = _normalize_query_value(params.get("question")).strip()
    autorun_value = _normalize_query_value(params.get("autorun")).strip().lower()
    top_k_raw = _normalize_query_value(params.get("top_k")).strip()
    mode_raw = _normalize_query_value(params.get("mode")).strip().lower()
    api_base_url = _normalize_query_value(params.get("api_base_url")).strip()

    mode_aliases = {
        UI_MODE_AUTO: UI_MODE_AUTO,
        UI_MODE_LOCAL: UI_MODE_LOCAL,
        UI_MODE_API: UI_MODE_API,
        "auto": UI_MODE_AUTO,
        "local": UI_MODE_LOCAL,
        "api": UI_MODE_API,
    }

    try:
        top_k = int(top_k_raw) if top_k_raw else None
    except ValueError:
        top_k = None

    return {
        "question": question,
        "autorun": autorun_value in {"1", "true", "yes", "y"},
        "top_k": top_k,
        "mode": mode_aliases.get(mode_raw, ""),
        "api_base_url": api_base_url,
    }


def format_answer_source(source: str) -> str:
    normalized = (source or "").strip().lower()
    mapping = {
        "api": "API",
        "local": "本地服务",
    }
    return mapping.get(normalized, (source or "未知来源").strip() or "未知来源")


def format_citation_meta(citation: Mapping[str, Any]) -> str:
    doc_name = str(citation.get("doc_name") or "-")
    source_title = str(citation.get("source_title") or "未识别资料题目")
    page_num = citation.get("page_num")
    page_text = str(page_num if page_num not in (None, "") else "?")
    score = citation.get("score")
    score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
    return (
        f"PDF 文件名：{doc_name} | "
        f"资料题目：{source_title} | "
        f"第 {page_text} 页 | "
        f"score：{score_text}"
    )


def build_citation_evidence_blocks(citation: Mapping[str, Any]) -> List[Tuple[str, str]]:
    quote_original = str(citation.get("quote_original") or citation.get("quote") or "").strip()
    quote_translation = str(citation.get("quote_translation") or "").strip()
    quote_language = str(citation.get("quote_language") or "").strip().lower()

    evidence_blocks: List[Tuple[str, str]] = []
    if quote_original:
        label = "英文证据" if quote_language == "en" else "证据原文"
        evidence_blocks.append((label, quote_original))
    if quote_language == "en" and quote_translation:
        evidence_blocks.append(("中文对照", quote_translation))
    return evidence_blocks


def render_style() -> None:
    st.markdown(
        """
        <style>
        :root {
          --paper-bg: #f7f1e3;
          --paper-card: #fffaf2;
          --paper-ink: #1d2b2a;
          --paper-accent: #0f766e;
          --paper-warm: #c66b3d;
          --paper-muted: #6a756f;
          --paper-line: rgba(29, 43, 42, 0.10);
        }
        .stApp {
          background:
            radial-gradient(circle at 12% 16%, rgba(198, 107, 61, 0.15), transparent 28%),
            radial-gradient(circle at 88% 12%, rgba(15, 118, 110, 0.16), transparent 24%),
            linear-gradient(180deg, #f8f1e8 0%, #efe4d0 100%);
          color: var(--paper-ink);
        }
        .block-container {
          max-width: 1180px;
          padding-top: 1.4rem;
          padding-bottom: 2.4rem;
        }
        .paper-hero {
          background: linear-gradient(135deg, rgba(255,250,242,0.92), rgba(240,229,209,0.88));
          border: 1px solid rgba(29,43,42,0.08);
          border-radius: 28px;
          padding: 1.4rem 1.5rem 1.2rem 1.5rem;
          box-shadow: 0 18px 50px rgba(82, 62, 37, 0.10);
          margin-bottom: 1rem;
        }
        .paper-kicker {
          color: var(--paper-accent);
          letter-spacing: 0.12em;
          text-transform: uppercase;
          font-size: 0.76rem;
          font-weight: 700;
          margin-bottom: 0.2rem;
        }
        .paper-title {
          font-size: 2.1rem;
          line-height: 1.05;
          font-weight: 700;
          color: var(--paper-ink);
          margin-bottom: 0.55rem;
          font-family: Georgia, "Times New Roman", serif;
        }
        .paper-subtitle {
          color: var(--paper-muted);
          font-size: 1rem;
          line-height: 1.6;
        }
        .metric-card, .answer-card, .citation-card, .status-card {
          background: rgba(255, 250, 242, 0.92);
          border: 1px solid var(--paper-line);
          border-radius: 22px;
          padding: 1rem 1rem 0.9rem 1rem;
          box-shadow: 0 10px 28px rgba(64, 47, 26, 0.06);
        }
        .metric-label {
          color: var(--paper-muted);
          font-size: 0.82rem;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .metric-value {
          font-size: 1.7rem;
          color: var(--paper-ink);
          font-weight: 700;
          margin-top: 0.25rem;
        }
        .metric-note {
          color: var(--paper-accent);
          font-size: 0.9rem;
          margin-top: 0.15rem;
        }
        .answer-title {
          color: var(--paper-accent);
          font-size: 0.85rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 0.45rem;
          font-weight: 700;
        }
        .answer-body {
          color: var(--paper-ink);
          font-size: 1rem;
          line-height: 1.75;
        }
        .citation-meta {
          color: var(--paper-accent);
          font-size: 0.84rem;
          font-weight: 700;
          margin-bottom: 0.35rem;
        }
        .citation-quote {
          color: var(--paper-ink);
          font-size: 0.96rem;
          line-height: 1.6;
        }
        .citation-label {
          color: var(--paper-muted);
          font-size: 0.78rem;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          margin-top: 0.6rem;
          margin-bottom: 0.18rem;
        }
        .citation-translation {
          border-top: 1px dashed rgba(29, 43, 42, 0.12);
          margin-top: 0.7rem;
          padding-top: 0.45rem;
        }
        .soft-note {
          color: var(--paper-muted);
          font-size: 0.93rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(snapshot: Dict[str, Any]) -> None:
    documents = snapshot["documents"]
    build_info = snapshot.get("build_info", {})
    health = snapshot["health"]
    answer_backend = health.get("answer_backend") or {}
    backend_value = answer_backend.get("active_backend", "extractive")
    backend_note = answer_backend.get("llm_model") or answer_backend.get("reason") or "fallback"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-label">Documents</div>
              <div class="metric-value">{documents.get('count', 0)}</div>
              <div class="metric-note">原始论文清单</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-label">Indexed</div>
              <div class="metric-value">{snapshot.get('indexed_count', 0)}</div>
              <div class="metric-note">已进入检索索引</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-label">Index Backend</div>
              <div class="metric-value">{build_info.get('backend', 'missing')}</div>
              <div class="metric-note">dim={build_info.get('vector_dim', 0)} | chunk_count={build_info.get('chunk_count', 0)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-label">Answer Backend</div>
              <div class="metric-value">{backend_value}</div>
              <div class="metric-note">{backend_note}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_documents_table(documents: List[Dict[str, Any]]) -> None:
    if not documents:
        st.info("当前没有可展示的文档。")
        return

    frame = pd.DataFrame(documents)
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        column_config={
            "doc_name": st.column_config.TextColumn("文档名"),
            "title": st.column_config.TextColumn("标题"),
            "page_count": st.column_config.NumberColumn("页数"),
            "status": st.column_config.TextColumn("状态"),
            "indexed": st.column_config.CheckboxColumn("已建索引"),
        },
    )


def render_answer(response_payload: Dict[str, Any], source: str) -> None:
    source_label = format_answer_source(source)
    if response_payload.get("answerable"):
        st.markdown(
            f"""
            <div class="answer-card">
              <div class="answer-title">回答来源：{html.escape(source_label)}</div>
              <div class="answer-body">{_escape_multiline_text(response_payload.get("answer", ""))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning(format_failure_message(response_payload))
        st.markdown(
            f"""
            <div class="status-card">
              <div class="answer-title">当前结论</div>
              <div class="answer-body">{_escape_multiline_text(response_payload.get("answer", ""))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    citations = response_payload.get("citations", [])
    if citations:
        st.subheader("引用证据")
        for citation in citations:
            evidence_blocks = build_citation_evidence_blocks(citation)
            evidence_html = "".join(
                (
                    f'<div class="citation-label">{html.escape(label)}</div>'
                    f'<div class="citation-quote">{_escape_multiline_text(text)}</div>'
                )
                if index == 0
                else (
                    f'<div class="citation-translation">'
                    f'<div class="citation-label">{html.escape(label)}</div>'
                    f'<div class="citation-quote">{_escape_multiline_text(text)}</div>'
                    f"</div>"
                )
                for index, (label, text) in enumerate(evidence_blocks)
            )
            st.markdown(
                f"""
                <div class="citation-card">
                  <div class="citation-meta">{html.escape(format_citation_meta(citation))}</div>
                  {evidence_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write("")

    retrieval = response_payload.get("retrieval") or {}
    if retrieval:
        with st.expander("检索元数据", expanded=False):
            st.json(retrieval)


def main() -> None:
    st.set_page_config(page_title="PaperLens Demo", page_icon="PL", layout="wide")
    render_style()

    settings = get_settings()
    st.session_state.setdefault("question_input", "")
    st.session_state.setdefault("response_payload", None)
    st.session_state.setdefault("response_source", "")
    st.session_state.setdefault("last_autorun_key", "")

    query_config = parse_demo_query_params(st.query_params)

    with st.sidebar:
        st.markdown("### Demo Control")
        mode_options = [UI_MODE_AUTO, UI_MODE_LOCAL, UI_MODE_API]
        initial_mode = query_config["mode"] if query_config["mode"] else UI_MODE_AUTO
        mode = st.selectbox("调用模式", mode_options, index=mode_options.index(initial_mode))
        default_api_base_url = query_config["api_base_url"] or DEFAULT_API_BASE_URL
        api_base_url = st.text_input("API Base URL", value=default_api_base_url)
        slider_top_k = query_config["top_k"] if query_config["top_k"] else settings.top_k
        top_k = st.slider("Top-K", min_value=3, max_value=12, value=int(slider_top_k))
        st.caption("默认优先尝试 API；若 API 不可用，会自动回退到本地 AnswerService。")

    snapshot, snapshot_notice = build_runtime_snapshot(mode, settings, api_base_url)

    if query_config["question"] and not st.session_state.get("question_input"):
        st.session_state["question_input"] = query_config["question"]

    st.markdown(
        """
        <section class="paper-hero">
          <div class="paper-kicker">Document RAG Demo</div>
          <div class="paper-title">PaperLens</div>
          <div class="paper-subtitle">
            从论文 PDF 到可引用回答。当前页面优先展示三种关键状态：
            索引是否就绪、问题是否可回答、证据引用是否完整返回。
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if snapshot_notice:
        st.info(snapshot_notice)

    render_metrics(snapshot)

    if not snapshot["health"].get("index_built"):
        st.error("索引尚未构建，当前无法进入问答。请先运行 `& .\\.venv\\Scripts\\python scripts\\build_index.py`。")

    autorun_top_k = query_config["top_k"] or top_k
    autorun_key = f"{mode}|{autorun_top_k}|{query_config['question']}"
    should_autorun = (
        query_config["autorun"]
        and bool(query_config["question"])
        and snapshot["health"].get("index_built")
        and st.session_state.get("last_autorun_key") != autorun_key
    )
    if should_autorun:
        try:
            payload, source = ask_question(
                mode,
                settings,
                api_base_url,
                query_config["question"],
                autorun_top_k,
            )
            st.session_state["question_input"] = query_config["question"]
            st.session_state["response_payload"] = payload
            st.session_state["response_source"] = source
            st.session_state["last_autorun_key"] = autorun_key
        except Exception as exc:
            st.error(f"自动演示运行失败：{exc}")

    tab_ask, tab_docs, tab_system = st.tabs(["Ask", "Documents", "System"])

    with tab_ask:
        autorun_demo = query_config["autorun"] and bool(query_config["question"])

        if autorun_demo and st.session_state.get("response_payload"):
            st.markdown("#### 自动演示结果")
            render_answer(
                st.session_state["response_payload"],
                st.session_state.get("response_source", ""),
            )
            st.caption("当前为 query-param 自动演示视图。去掉 `autorun=1` 后可恢复完整交互表单。")
        else:
            st.markdown("#### 示例问题")
            example_questions = load_example_questions(settings)
            if example_questions:
                button_cols = st.columns(2)
                for index, question in enumerate(example_questions[:6]):
                    if button_cols[index % 2].button(
                        question,
                        key=f"example_{index}",
                        use_container_width=True,
                    ):
                        st.session_state["question_input"] = question

            with st.form("ask_form", clear_on_submit=False):
                question = st.text_area(
                    "输入问题",
                    value=st.session_state.get("question_input", ""),
                    placeholder="例如：LayoutLM 在文档理解里最核心的建模对象是什么？",
                    height=120,
                )
                submitted = st.form_submit_button("Ask PaperLens", use_container_width=True)

            if submitted:
                st.session_state["question_input"] = question
                if not question.strip():
                    st.warning("请输入一个具体问题。")
                elif not snapshot["health"].get("index_built"):
                    st.error("当前未构建索引，无法执行问答。")
                else:
                    with st.spinner("正在检索文档并生成带引用回答..."):
                        try:
                            payload, source = ask_question(mode, settings, api_base_url, question.strip(), top_k)
                            st.session_state["response_payload"] = payload
                            st.session_state["response_source"] = source
                        except (IndexNotBuiltError, FileNotFoundError) as exc:
                            st.error(str(exc))
                        except PaperLensRagError as exc:
                            st.error(f"PaperLens 运行失败：{exc}")
                        except requests.RequestException as exc:
                            st.error(f"API 调用失败：{exc}")
                        except Exception as exc:
                            st.error(f"出现未预期错误：{exc}")

        if st.session_state.get("response_payload") and not autorun_demo:
            render_answer(
                st.session_state["response_payload"],
                st.session_state.get("response_source", ""),
            )
        else:
            st.markdown(
                """
                <div class="status-card">
                  <div class="answer-title">Ready</div>
                  <div class="soft-note">
                    输入一个问题后，页面会展示答案、是否拒答，以及按文档页码组织的证据引用。
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab_docs:
        st.markdown("#### 文档清单")
        render_documents_table(snapshot["documents"].get("documents", []))

    with tab_system:
        col_left, col_right = st.columns([1.05, 0.95])
        with col_left:
            st.markdown("#### 运行状态")
            st.json(snapshot["health"])
        with col_right:
            st.markdown("#### 索引摘要")
            st.json(snapshot.get("build_info", {}))
        st.markdown("#### 说明")
        st.markdown(
            """
            - `未构建索引`：页面会直接阻止问答，并给出构建命令。
            - `无法回答`：页面会展示拒答文案和 `failure_reason`。
            - `引用列表`：每条回答都尽量附带文档名、页码、chunk id 和证据片段。
            """
        )
