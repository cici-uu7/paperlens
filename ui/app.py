"""Thin Streamlit entrypoint for the PaperLens demo."""

from __future__ import annotations

import sys
from pathlib import Path


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

current_app_module = sys.modules.get("app")
if current_app_module is not None:
    current_module_file = getattr(current_app_module, "__file__", "")
    if current_module_file and Path(current_module_file).resolve() == Path(__file__).resolve():
        sys.modules["paperlens_ui_entry"] = current_app_module
        del sys.modules["app"]

from ui.streamlit_app import (  # noqa: E402
    DEFAULT_API_BASE_URL,
    UI_MODE_API,
    UI_MODE_AUTO,
    UI_MODE_LOCAL,
    build_local_snapshot,
    format_failure_message,
    load_example_questions,
    main,
    parse_demo_query_params,
)


__all__ = [
    "DEFAULT_API_BASE_URL",
    "UI_MODE_API",
    "UI_MODE_AUTO",
    "UI_MODE_LOCAL",
    "build_local_snapshot",
    "format_failure_message",
    "load_example_questions",
    "main",
    "parse_demo_query_params",
]


if __name__ == "__main__":
    main()
