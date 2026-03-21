"""XMind 文件反向解析器。

读取 ``.xmind`` ZIP 归档中的 ``content.json``，解析为
``XMindReferenceNode`` 树结构。

仅支持 XMind 8+ 格式（``content.json``），旧格式（``content.xml``）
将抛出 ``UnsupportedXMindFormatError``。
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path

from app.domain.xmind_reference_models import XMindReferenceNode

logger = logging.getLogger(__name__)


class XMindParseError(Exception):
    """XMind 文件解析错误。"""


class UnsupportedXMindFormatError(XMindParseError):
    """不支持的 XMind 格式（旧版 content.xml）。"""


class XMindParser:
    """XMind 文件反向解析器。

    将 .xmind ZIP 归档解析为 ``XMindReferenceNode`` 树。
    遵循项目 parsers 层 Protocol + 具体实现的模式。
    """

    def parse(self, file_path: str) -> XMindReferenceNode:
        """解析 .xmind 文件，返回根节点树结构。

        Args:
            file_path: .xmind 文件的本地路径。

        Returns:
            根节点 ``XMindReferenceNode``。

        Raises:
            FileNotFoundError: 文件不存在。
            XMindParseError: ZIP 损坏或缺少 content.json。
            UnsupportedXMindFormatError: 仅有 content.xml（旧格式）。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"XMind file not found: {file_path}")

        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                if "content.json" not in names:
                    if "content.xml" in names:
                        raise UnsupportedXMindFormatError(
                            f"XMind 旧格式（content.xml）不支持，"
                            f"请使用 XMind 8+ 版本保存: {file_path}"
                        )
                    raise XMindParseError(
                        f"XMind 文件中未找到 content.json: {file_path}"
                    )
                raw = zf.read("content.json")
        except zipfile.BadZipFile as exc:
            raise XMindParseError(
                f"XMind 文件损坏或不是有效的 ZIP 归档: {file_path}"
            ) from exc

        try:
            sheets = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise XMindParseError(
                f"content.json JSON 解析失败: {exc}"
            ) from exc

        if not isinstance(sheets, list) or len(sheets) == 0:
            raise XMindParseError(
                f"content.json 格式异常（期望非空数组）: {file_path}"
            )

        root_topic = sheets[0].get("rootTopic")
        if root_topic is None:
            raise XMindParseError(
                f"content.json 中缺少 rootTopic: {file_path}"
            )

        return self._parse_topic(root_topic)

    def _parse_topic(self, topic: dict) -> XMindReferenceNode:
        """递归解析 XMind topic 节点。

        XMind 8+ 格式中子节点位于 ``topic["children"]["attached"]``。
        部分变体可能直接使用列表格式，兼容处理。
        """
        title = topic.get("title", "")
        children_data = topic.get("children", {})

        attached: list[dict] = []
        if isinstance(children_data, dict):
            attached = children_data.get("attached", [])
        elif isinstance(children_data, list):
            # 兼容某些 XMind 变体的直接列表格式
            attached = children_data

        child_nodes = [self._parse_topic(child) for child in attached]
        return XMindReferenceNode(title=title, children=child_nodes)
