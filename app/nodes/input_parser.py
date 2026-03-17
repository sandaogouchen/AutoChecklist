"""输入解析节点。

工作流的第一个节点：从 state 中获取文件路径，
选择合适的解析器将 PRD 文档解析为结构化的 ``ParsedDocument``。
"""

from __future__ import annotations

from pathlib import Path

from app.domain.state import GlobalState
from app.parsers.factory import get_parser


def input_parser_node(state: GlobalState) -> GlobalState:
    """解析输入文档并将结果写入工作流状态。

    读取 state 中的 ``file_path``（或从 ``request`` 对象中提取），
    通过工厂函数获取对应解析器，完成文档解析。

    Returns:
        包含 ``parsed_document`` 的状态增量。
    """
    file_path = _resolve_file_path(state)
    parser = get_parser(file_path)
    parsed_document = parser.parse(file_path)
    return {"parsed_document": parsed_document}


def _resolve_file_path(state: GlobalState) -> Path:
    """从工作流状态中解析出有效的文件绝对路径。

    路径查找优先级：
    1. ``state["file_path"]`` — 直接指定
    2. ``state["request"].file_path`` — 从请求对象提取

    对于相对路径，会以当前工作目录（cwd）为基准转换为绝对路径。

    Raises:
        ValueError: 状态中未提供 file_path。
        FileNotFoundError: 解析后的路径不存在。
    """
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
