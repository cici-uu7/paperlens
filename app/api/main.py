"""FastAPI app for the PaperLens demo."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.rag import AnswerService, IndexNotBuiltError, PaperLensRagError
from app.services.manifest_service import scan_raw_docs


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: Optional[int] = Field(default=None, ge=1, le=20)


def _load_indexed_doc_names(index_dir: Path) -> Set[str]:
    metadata_path = Path(index_dir) / "chunk_metadata.jsonl"
    if not metadata_path.exists():
        return set()

    doc_names: Set[str] = set()
    with metadata_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            doc_name = payload.get("doc_name")
            if doc_name:
                doc_names.add(str(doc_name))
    return doc_names


def _load_manifest_rows(settings: Settings) -> List[Dict[str, Any]]:
    runtime_manifest = settings.reports_dir / "doc_manifest_runtime.csv"
    if runtime_manifest.exists():
        with runtime_manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    return [record.to_row() for record in scan_raw_docs(settings)]


def create_app(
    settings: Optional[Settings] = None,
    answer_service_factory: Optional[Callable[[], Any]] = None,
) -> FastAPI:
    app = FastAPI(title="PaperLens API", version="0.1.0")
    app.state.settings = settings or get_settings()
    app.state.answer_service_factory = (
        answer_service_factory
        or (lambda: AnswerService.from_settings(app.state.settings))
    )

    @app.get("/health")
    def health() -> Dict[str, Any]:
        indexed = (app.state.settings.index_dir / "build_info.json").exists()
        answer_backend = AnswerService.describe_backend(app.state.settings)
        return {
            "status": "ok",
            "index_built": indexed,
            "raw_docs_dir": str(app.state.settings.raw_docs_dir),
            "answer_backend": answer_backend,
        }

    @app.get("/documents")
    def documents() -> Dict[str, Any]:
        rows = _load_manifest_rows(app.state.settings)
        indexed_doc_names = _load_indexed_doc_names(app.state.settings.index_dir)
        documents = [
            {
                "doc_name": row.get("filename", ""),
                "title": row.get("title", ""),
                "page_count": int(row["page_count"]) if row.get("page_count") else None,
                "status": row.get("status", ""),
                "indexed": row.get("filename", "") in indexed_doc_names,
            }
            for row in rows
        ]
        return {"count": len(documents), "documents": documents}

    @app.post("/ask")
    def ask(request: AskRequest) -> Dict[str, Any]:
        try:
            service = app.state.answer_service_factory()
            response = service.answer_question(request.question, top_k=request.top_k)
        except IndexNotBuiltError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except PaperLensRagError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive API fallback
            raise HTTPException(status_code=500, detail=f"Unexpected PaperLens error: {exc}") from exc
        return response.to_dict()

    return app


app = create_app()
