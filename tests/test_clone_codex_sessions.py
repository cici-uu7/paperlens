import importlib.util
import json
import sys
from pathlib import Path
from typing import Optional

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "clone_codex_sessions.py"


def _load_clone_module():
    spec = importlib.util.spec_from_file_location("clone_codex_sessions", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_session(
    root: Path,
    *,
    relative_path: str,
    session_id: str,
    provider: str,
    cwd: str,
    extra_payload: Optional[dict] = None,
) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": session_id,
        "model_provider": provider,
        "cwd": cwd,
    }
    if extra_payload:
        payload.update(extra_payload)
    record = {
        "timestamp": "2026-04-03T00:00:00+00:00",
        "type": "session_meta",
        "payload": payload,
    }
    path.write_text(
        json.dumps(record, ensure_ascii=False) + "\n"
        + json.dumps({"type": "message", "payload": {"role": "user"}})
        + "\n",
        encoding="utf-8",
    )
    return path


def test_select_sources_can_target_other_providers_for_one_workspace(tmp_path):
    module = _load_clone_module()
    repo_dir = tmp_path / "paperlens"
    repo_dir.mkdir()

    _write_session(
        tmp_path,
        relative_path="2026/04/03/custom.jsonl",
        session_id="custom-session",
        provider="custom",
        cwd=str(repo_dir),
    )
    _write_session(
        tmp_path,
        relative_path="2026/04/03/openai.jsonl",
        session_id="openai-session",
        provider="openai",
        cwd=str(repo_dir),
    )
    _write_session(
        tmp_path,
        relative_path="2026/04/03/OpenAI.jsonl",
        session_id="openai-title-case-session",
        provider="OpenAI",
        cwd=str(repo_dir),
    )
    _write_session(
        tmp_path,
        relative_path="2026/04/03/other-workspace.jsonl",
        session_id="other-workspace-session",
        provider="custom",
        cwd=str(tmp_path / "another-workspace"),
    )

    selected = module.select_sources(
        sessions_dir=tmp_path,
        source_providers=set(),
        target_provider="openai",
        other_providers=True,
        requested_ids=set(),
        cwd_filters={module.normalize_cwd(str(repo_dir))},
    )

    selected_ids = {meta.session_id for meta in selected}
    assert selected_ids == {"custom-session", "openai-title-case-session"}


def test_main_other_providers_reports_existing_and_new_restore_candidates(
    tmp_path, monkeypatch, capsys
):
    module = _load_clone_module()
    repo_dir = tmp_path / "paperlens"
    repo_dir.mkdir()

    _write_session(
        tmp_path,
        relative_path="2026/04/03/custom.jsonl",
        session_id="custom-session",
        provider="custom",
        cwd=str(repo_dir),
    )
    _write_session(
        tmp_path,
        relative_path="2026/04/03/openai-clone.jsonl",
        session_id="restored-openai-session",
        provider="openai",
        cwd=str(repo_dir),
        extra_payload={
            "cloned_from": "custom-session",
            "original_provider": "custom",
        },
    )
    _write_session(
        tmp_path,
        relative_path="2026/04/03/OpenAI.jsonl",
        session_id="openai-title-case-session",
        provider="OpenAI",
        cwd=str(repo_dir),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clone_codex_sessions.py",
            "--sessions-dir",
            str(tmp_path),
            "--cwd",
            str(repo_dir),
            "--other-providers",
            "--target-provider",
            "openai",
            "--dry-run",
        ],
    )

    exit_code = module.main()
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert "source_selector=other-providers" in stdout
    assert "matched=2" in stdout
    assert "new=1" in stdout
    assert "existing=1" in stdout
    assert "[exists] restored-openai-session cloned_from=custom-session" in stdout
    assert "[clone] openai-title-case-session -> " in stdout


def test_main_rejects_mixing_other_providers_with_explicit_source_provider(tmp_path, monkeypatch):
    module = _load_clone_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "clone_codex_sessions.py",
            "--sessions-dir",
            str(tmp_path),
            "--cwd",
            str(tmp_path),
            "--source-provider",
            "custom",
            "--other-providers",
        ],
    )

    with pytest.raises(SystemExit, match="Use --other-providers or --source-provider, not both."):
        module.main()
