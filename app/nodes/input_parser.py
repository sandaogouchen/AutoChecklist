from __future__ import annotations

from pathlib import Path

from app.domain.state import GlobalState
from app.parsers.factory import get_parser


def input_parser_node(state: GlobalState) -> GlobalState:
    file_path = _resolve_file_path(state)
    parser = get_parser(file_path)
    parsed_document = parser.parse(file_path)
    return {"parsed_document": parsed_document}


def _resolve_file_path(state: GlobalState) -> Path:
    raw_path = state.get("file_path")
    if not raw_path and state.get("request"):
        raw_path = state["request"].file_path
    if not raw_path:
        raise ValueError("Workflow state is missing file_path")

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(path)
    return path.resolve()
