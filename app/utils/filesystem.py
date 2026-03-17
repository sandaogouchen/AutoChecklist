"""文件系统工具函数。

封装了常用的文件操作（目录创建、JSON 读写、文本写入），
为仓储层和其他需要文件 IO 的模块提供统一的基础设施。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def ensure_directory(path: str | Path) -> Path:
    """确保目录存在，不存在则递归创建。

    Args:
        path: 目标目录路径。

    Returns:
        目录的 Path 对象。
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_json(path: str | Path, payload: Any) -> Path:
    """将数据序列化为格式化的 JSON 并写入文件。

    自动处理 Pydantic 模型、嵌套字典和列表的序列化。
    父目录不存在时会自动创建。

    Args:
        path: 目标文件路径。
        payload: 待序列化的数据（支持 dict / list / BaseModel）。

    Returns:
        写入的文件路径。
    """
    target = Path(path)
    ensure_directory(target.parent)
    target.write_text(
        json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def read_json(path: str | Path) -> dict[str, Any]:
    """从文件中读取并反序列化 JSON 数据。

    Raises:
        FileNotFoundError: 文件不存在。
        json.JSONDecodeError: 文件内容不是合法的 JSON。
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path: str | Path, content: str) -> Path:
    """将纯文本内容写入文件，父目录不存在时自动创建。

    Args:
        path: 目标文件路径。
        content: 文本内容。

    Returns:
        写入的文件路径。
    """
    target = Path(path)
    ensure_directory(target.parent)
    target.write_text(content, encoding="utf-8")
    return target


def _to_jsonable(payload: Any) -> Any:
    """递归地将 payload 转换为 JSON 可序列化的原生类型。

    转换规则：
    - ``BaseModel`` → 调用 ``model_dump(mode="json")``
    - ``dict`` → 递归处理每个值
    - ``list`` → 递归处理每个元素
    - 其他类型 → 原样返回（交给 json.dumps 处理）
    """
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _to_jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_to_jsonable(item) for item in payload]
    return payload
