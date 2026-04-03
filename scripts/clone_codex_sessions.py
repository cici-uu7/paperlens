"""Clone local Codex sessions from one provider label to another."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


@dataclass(frozen=True)
class SessionMeta:
    path: Path
    session_id: str
    model_provider: str
    record_timestamp: str | None
    payload: dict


@dataclass(frozen=True)
class ClonePlan:
    source: SessionMeta
    clone_id: str
    target_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clone Codex local session files from one provider label to another "
            "without changing the original files."
        )
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=DEFAULT_SESSIONS_DIR,
        help=f"Session root directory. Defaults to {DEFAULT_SESSIONS_DIR}.",
    )
    parser.add_argument(
        "--source-provider",
        action="append",
        default=[],
        help=(
            "Source provider label in session_meta payload. Can be passed "
            'multiple times. Defaults to "custom" unless --other-providers is used.'
        ),
    )
    parser.add_argument(
        "--target-provider",
        default="openai",
        help='Target provider label in session_meta payload. Defaults to "openai".',
    )
    parser.add_argument(
        "--other-providers",
        action="store_true",
        help=(
            "Clone sessions from every provider label except --target-provider. "
            "Useful when the same workspace history is split across multiple vendors."
        ),
    )
    parser.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Specific source session id to clone. Can be passed multiple times.",
    )
    parser.add_argument(
        "--cwd",
        action="append",
        default=[],
        help=(
            "Only clone sessions whose session_meta payload cwd matches this "
            "directory path. Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clone every session that matches the selected source provider filter.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be cloned without writing any files.",
    )
    return parser.parse_args()


def iter_session_files(sessions_dir: Path) -> Iterable[Path]:
    yield from sorted(sessions_dir.rglob("*.jsonl"))


def normalize_cwd(value: str) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).expanduser())))


def load_session_meta(path: Path) -> SessionMeta | None:
    try:
        first_line = path.open("r", encoding="utf-8").readline()
    except OSError as exc:
        print(f"[warn] failed to read {path}: {exc}", file=sys.stderr)
        return None

    if not first_line:
        return None

    try:
        record = json.loads(first_line)
    except json.JSONDecodeError as exc:
        print(f"[warn] invalid JSON in first line of {path}: {exc}", file=sys.stderr)
        return None

    if record.get("type") != "session_meta":
        return None

    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None

    session_id = payload.get("id")
    model_provider = payload.get("model_provider")
    if not isinstance(session_id, str) or not isinstance(model_provider, str):
        return None

    return SessionMeta(
        path=path,
        session_id=session_id,
        model_provider=model_provider,
        record_timestamp=record.get("timestamp"),
        payload=payload,
    )


def build_existing_clone_index(sessions_dir: Path) -> dict[tuple[str, str], SessionMeta]:
    index: dict[tuple[str, str], SessionMeta] = {}
    for path in iter_session_files(sessions_dir):
        meta = load_session_meta(path)
        if meta is None:
            continue
        cloned_from = meta.payload.get("cloned_from")
        if isinstance(cloned_from, str):
            index[(cloned_from, meta.model_provider)] = meta
    return index


def session_matches_source_selection(
    *,
    model_provider: str,
    source_providers: set[str],
    target_provider: str,
    other_providers: bool,
) -> bool:
    if other_providers:
        return model_provider != target_provider
    return model_provider in source_providers


def select_sources(
    sessions_dir: Path,
    source_providers: set[str],
    target_provider: str,
    other_providers: bool,
    requested_ids: set[str],
    cwd_filters: set[str] | None,
) -> list[SessionMeta]:
    selected: list[SessionMeta] = []
    for path in iter_session_files(sessions_dir):
        meta = load_session_meta(path)
        if meta is None:
            continue
        if not session_matches_source_selection(
            model_provider=meta.model_provider,
            source_providers=source_providers,
            target_provider=target_provider,
            other_providers=other_providers,
        ):
            continue
        if requested_ids and meta.session_id not in requested_ids:
            continue
        if cwd_filters is not None:
            session_cwd = meta.payload.get("cwd")
            if not isinstance(session_cwd, str):
                continue
            if normalize_cwd(session_cwd) not in cwd_filters:
                continue
        selected.append(meta)
    return selected


def make_clone_path(source: SessionMeta, clone_id: str) -> Path:
    source_name = source.path.name
    if source.session_id in source_name:
        clone_name = source_name.replace(source.session_id, clone_id, 1)
    else:
        clone_name = f"{source.path.stem}-{clone_id}.jsonl"
    return source.path.with_name(clone_name)


def build_clone_plan(
    source: SessionMeta,
    existing_clones: dict[tuple[str, str], SessionMeta],
    target_provider: str,
) -> tuple[str, ClonePlan | SessionMeta]:
    existing = existing_clones.get((source.session_id, target_provider))
    if existing is not None:
        return "exists", existing

    clone_id = str(uuid.uuid4())
    return "new", ClonePlan(
        source=source,
        clone_id=clone_id,
        target_path=make_clone_path(source, clone_id),
    )


def rewrite_first_record(source: SessionMeta, clone_id: str, target_provider: str) -> str:
    session_meta_record = {
        "timestamp": source.record_timestamp,
        "type": "session_meta",
        "payload": dict(source.payload),
    }
    payload = session_meta_record["payload"]
    payload["id"] = clone_id
    payload["model_provider"] = target_provider
    payload["cloned_from"] = source.session_id
    payload["original_provider"] = source.model_provider
    payload["clone_timestamp"] = datetime.now(timezone.utc).isoformat()
    return json.dumps(session_meta_record, ensure_ascii=False, separators=(",", ":")) + "\n"


def materialize_clone(plan: ClonePlan, target_provider: str, dry_run: bool) -> None:
    new_first_line = rewrite_first_record(plan.source, plan.clone_id, target_provider)
    if dry_run:
        return

    plan.target_path.parent.mkdir(parents=True, exist_ok=True)
    with plan.source.path.open("r", encoding="utf-8") as source_handle:
        lines = source_handle.readlines()

    if not lines:
        raise ValueError(f"source session is empty: {plan.source.path}")

    lines[0] = new_first_line
    with plan.target_path.open("w", encoding="utf-8", newline="") as target_handle:
        target_handle.writelines(lines)


def describe_source_selection(
    source_providers: set[str],
    other_providers: bool,
) -> str:
    if other_providers:
        return "other-providers"
    return ",".join(sorted(source_providers))


def main() -> int:
    args = parse_args()
    sessions_dir = args.sessions_dir.expanduser().resolve()
    requested_ids = set(args.session_id)
    cwd_filters = {normalize_cwd(value) for value in args.cwd} or None
    explicit_source_providers = set(args.source_provider)

    if args.other_providers and explicit_source_providers:
        raise SystemExit("Use --other-providers or --source-provider, not both.")

    source_providers = explicit_source_providers or (
        set() if args.other_providers else {"custom"}
    )
    source_selector = describe_source_selection(source_providers, args.other_providers)

    if not args.all and not requested_ids and cwd_filters is None:
        raise SystemExit("Pass --session-id <uuid>, --cwd <path>, or use --all.")
    if args.other_providers is False and args.target_provider in source_providers:
        raise SystemExit("--source-provider values must differ from --target-provider.")
    if not sessions_dir.exists():
        raise SystemExit(f"Sessions directory does not exist: {sessions_dir}")

    existing_clones = build_existing_clone_index(sessions_dir)
    sources = select_sources(
        sessions_dir=sessions_dir,
        source_providers=source_providers,
        target_provider=args.target_provider,
        other_providers=args.other_providers,
        requested_ids=requested_ids,
        cwd_filters=cwd_filters,
    )

    if requested_ids:
        found_ids = {source.session_id for source in sources}
        missing_ids = sorted(requested_ids - found_ids)
        for missing_id in missing_ids:
            print(
                "[warn] session id not found under provider selector "
                + source_selector
                + ": "
                + missing_id
            )

    if not sources:
        print("No matching source sessions found.")
        return 0

    planned: list[ClonePlan] = []
    reused: list[SessionMeta] = []
    for source in sources:
        status, payload = build_clone_plan(source, existing_clones, args.target_provider)
        if status == "exists":
            reused.append(payload)
        else:
            planned.append(payload)

    print(
        "sessions_dir="
        + str(sessions_dir)
        + (
            " cwd_filter=" + next(iter(cwd_filters))
            if cwd_filters is not None and len(cwd_filters) == 1
            else ""
        )
        + (
            " cwd_filter_count=" + str(len(cwd_filters))
            if cwd_filters is not None and len(cwd_filters) > 1
            else ""
        )
        + " source_selector="
        + source_selector
        + " target_provider="
        + args.target_provider
        + " matched="
        + str(len(sources))
        + " new="
        + str(len(planned))
        + " existing="
        + str(len(reused))
        + " dry_run="
        + str(bool(args.dry_run)).lower()
    )

    for existing in reused:
        print(
            "[exists] "
            + existing.session_id
            + " cloned_from="
            + str(existing.payload.get("cloned_from"))
            + " path="
            + str(existing.path)
        )

    for plan in planned:
        print(
            "[clone] "
            + plan.source.session_id
            + " -> "
            + plan.clone_id
            + " path="
            + str(plan.target_path)
        )
        materialize_clone(plan, args.target_provider, args.dry_run)

    clone_ids = [plan.clone_id for plan in planned]
    if not args.dry_run and clone_ids:
        print()
        print("resume_commands:")
        for clone_id in clone_ids:
            print(f"  codex resume {clone_id}")
    elif args.dry_run and planned:
        print()
        print("dry_run_resume_examples:")
        for plan in planned:
            print(f"  codex resume {plan.clone_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
