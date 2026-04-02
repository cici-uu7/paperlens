"""Runtime configuration helpers for PaperLens."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv


_PAPERLENS_ENV_NAMES = [
    "PARSER_BACKEND",
    "EMBEDDING_BACKEND",
    "ANSWER_BACKEND",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "LLM_MODEL",
    "OPENAI_MODEL",
    "EMBEDDING_MODEL",
    "TOP_K",
    "CHUNK_MAX_CHARS",
    "CHUNK_OVERLAP",
    "RETRIEVAL_SCORE_THRESHOLD",
    "LLM_TEMPERATURE",
    "LLM_MAX_CONTEXT_CHUNKS",
    "LLM_MAX_OUTPUT_TOKENS",
]


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def load_environment(
    env_path: Optional[Path] = None,
    *,
    reset_known_keys: bool = False,
) -> Path:
    target = Path(env_path) if env_path else _default_project_root() / ".env"
    if reset_known_keys:
        for name in _PAPERLENS_ENV_NAMES:
            os.environ.pop(name, None)
    if target.exists():
        load_dotenv(target, override=reset_known_keys)
    return target


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    raw_docs_dir: Path
    parsed_docs_dir: Path
    opendataloader_raw_dir: Path
    normalized_docs_dir: Path
    chunk_dir: Path
    index_dir: Path
    eval_dir: Path
    reports_dir: Path
    logs_dir: Path
    parser_backend: str
    embedding_backend: str
    answer_backend: str
    openai_api_key: str
    openai_base_url: str
    llm_model: str
    embedding_model: str
    top_k: int
    chunk_max_chars: int
    chunk_overlap: int
    retrieval_score_threshold: float
    llm_temperature: float
    llm_max_context_chunks: int
    llm_max_output_tokens: int

    @classmethod
    def from_env(
        cls,
        project_root: Optional[Path] = None,
        env_path: Optional[Path] = None,
    ) -> "Settings":
        root = Path(project_root).resolve() if project_root else _default_project_root()
        load_environment(
            env_path or root / ".env",
            reset_known_keys=env_path is not None,
        )
        data_dir = root / "data"
        return cls(
            project_root=root,
            data_dir=data_dir,
            raw_docs_dir=data_dir / "raw_docs",
            parsed_docs_dir=data_dir / "parsed_docs",
            opendataloader_raw_dir=data_dir / "parsed_docs" / "opendataloader_raw",
            normalized_docs_dir=data_dir / "parsed_docs" / "normalized",
            chunk_dir=data_dir / "chunks",
            index_dir=data_dir / "indexes",
            eval_dir=data_dir / "eval",
            reports_dir=root / "reports",
            logs_dir=root / "logs",
            parser_backend=os.getenv("PARSER_BACKEND", "pymupdf"),
            embedding_backend=os.getenv("EMBEDDING_BACKEND", "auto"),
            answer_backend=os.getenv("ANSWER_BACKEND", "auto"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
            llm_model=os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "")),
            embedding_model=os.getenv("EMBEDDING_MODEL", ""),
            top_k=_get_int("TOP_K", 5),
            chunk_max_chars=_get_int("CHUNK_MAX_CHARS", 1400),
            chunk_overlap=_get_int("CHUNK_OVERLAP", 200),
            retrieval_score_threshold=_get_float("RETRIEVAL_SCORE_THRESHOLD", 0.25),
            llm_temperature=_get_float("LLM_TEMPERATURE", 0.0),
            llm_max_context_chunks=_get_int("LLM_MAX_CONTEXT_CHUNKS", 6),
            llm_max_output_tokens=_get_int("LLM_MAX_OUTPUT_TOKENS", 400),
        )

    def runtime_directories(self) -> List[Path]:
        return [
            self.raw_docs_dir,
            self.parsed_docs_dir,
            self.opendataloader_raw_dir,
            self.normalized_docs_dir,
            self.chunk_dir,
            self.index_dir,
            self.eval_dir,
            self.reports_dir,
            self.logs_dir,
        ]

    def ensure_runtime_dirs(self) -> List[Path]:
        created: List[Path] = []
        for path in self.runtime_directories():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
        return created

    def as_dict(self) -> Dict[str, str]:
        return {
            "project_root": str(self.project_root),
            "data_dir": str(self.data_dir),
            "raw_docs_dir": str(self.raw_docs_dir),
            "parsed_docs_dir": str(self.parsed_docs_dir),
            "opendataloader_raw_dir": str(self.opendataloader_raw_dir),
            "normalized_docs_dir": str(self.normalized_docs_dir),
            "chunk_dir": str(self.chunk_dir),
            "index_dir": str(self.index_dir),
            "eval_dir": str(self.eval_dir),
            "reports_dir": str(self.reports_dir),
            "logs_dir": str(self.logs_dir),
            "parser_backend": self.parser_backend,
            "embedding_backend": self.embedding_backend,
            "answer_backend": self.answer_backend,
            "openai_api_key": self.openai_api_key,
            "openai_base_url": self.openai_base_url,
            "llm_model": self.llm_model,
            "embedding_model": self.embedding_model,
            "top_k": str(self.top_k),
            "chunk_max_chars": str(self.chunk_max_chars),
            "chunk_overlap": str(self.chunk_overlap),
            "retrieval_score_threshold": str(self.retrieval_score_threshold),
            "llm_temperature": str(self.llm_temperature),
            "llm_max_context_chunks": str(self.llm_max_context_chunks),
            "llm_max_output_tokens": str(self.llm_max_output_tokens),
        }


def get_settings(
    project_root: Optional[Path] = None,
    env_path: Optional[Path] = None,
) -> Settings:
    return Settings.from_env(project_root=project_root, env_path=env_path)
