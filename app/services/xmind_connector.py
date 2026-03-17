"""XMind 连接器。

定义了 XMind 连接器的协议接口和基于文件系统的默认实现。
``FileXMindConnector`` 使用标准库 ``zipfile`` + ``json`` 生成
符合 XMind 8/Zen 格式的 ``.xmind`` 文件（实质为 ZIP 归档）。

.xmind 文件结构：
- ``content.json``：包含一个 sheet 对象数组，每个 sheet 有 rootTopic
- ``metadata.json``：创建者元数据
- ``manifest.json``：文件清单
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from app.domain.xmind_models import XMindDeliveryResult, XMindNode

logger = logging.getLogger(__name__)


@runtime_checkable
class XMindConnector(Protocol):
    """XMind 连接器协议。

    定义了生成思维导图文件的标准接口，
    允许替换为不同的实现（本地文件、云端 API 等）。
    """

    def create_map(self, root_node: XMindNode, title: str) -> XMindDeliveryResult:
        """根据节点树创建 XMind 思维导图。

        Args:
            root_node: 思维导图的根节点。
            title: 思维导图标题。

        Returns:
            交付结果，包含文件路径或错误信息。
        """
        ...

    def health_check(self) -> bool:
        """检查连接器是否可用。

        Returns:
            连接器可用返回 True，否则返回 False。
        """
        ...


class FileXMindConnector:
    """基于文件系统的 XMind 连接器。

    将 ``XMindNode`` 树序列化为 XMind 8/Zen 兼容的 ``.xmind`` 文件。
    该文件本质上是一个 ZIP 归档，内部包含以下 JSON 文件：
    - ``content.json``：思维导图内容（sheet + topic 层次结构）
    - ``metadata.json``：创建者信息
    - ``manifest.json``：文件清单
    """

    def __init__(self, output_dir: str | Path) -> None:
        """初始化文件连接器。

        Args:
            output_dir: .xmind 文件的输出目录。
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_map(self, root_node: XMindNode, title: str) -> XMindDeliveryResult:
        """生成 .xmind 文件。

        Args:
            root_node: 思维导图的根节点。
            title: 思维导图标题，同时用于生成文件名。

        Returns:
            交付结果，成功时包含文件路径。
        """
        try:
            # 生成唯一文件名，避免冲突
            safe_title = _sanitize_filename(title)
            file_name = f"{safe_title}_{uuid4().hex[:8]}.xmind"
            file_path = self.output_dir / file_name

            # 构建 XMind JSON 内容
            root_topic = _node_to_topic(root_node)
            sheet_id = uuid4().hex
            content = [
                {
                    "id": sheet_id,
                    "class": "sheet",
                    "title": title,
                    "rootTopic": root_topic,
                }
            ]

            metadata = {
                "creator": {
                    "name": "AutoChecklist",
                    "version": "0.1.0",
                },
            }

            manifest = {
                "file-entries": {
                    "content.json": {},
                    "metadata.json": {},
                },
            }

            # 写入 ZIP 归档
            with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
                zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

            logger.info("XMind 文件已生成: %s", file_path)

            return XMindDeliveryResult(
                success=True,
                file_path=str(file_path),
            )

        except Exception as exc:
            logger.exception("生成 XMind 文件失败: %s", exc)
            return XMindDeliveryResult(
                success=False,
                error_message=f"生成 XMind 文件失败: {exc}",
            )

    def health_check(self) -> bool:
        """检查输出目录是否可写。"""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.output_dir / ".health_check"
            test_file.write_text("ok")
            test_file.unlink()
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _node_to_topic(node: XMindNode) -> dict:
    """将 ``XMindNode`` 递归转换为 XMind JSON topic 结构。

    Args:
        node: 思维导图节点。

    Returns:
        符合 XMind content.json 规范的 topic 字典。
    """
    topic: dict = {
        "id": uuid4().hex,
        "class": "topic",
        "title": node.title,
    }

    # 添加子节点
    if node.children:
        attached = [_node_to_topic(child) for child in node.children]
        topic["children"] = {"attached": attached}

    # 添加标记（markers）
    if node.markers:
        topic["markers"] = [{"markerId": marker} for marker in node.markers]

    # 添加备注
    if node.notes:
        topic["notes"] = {
            "plain": {
                "content": node.notes,
            },
        }

    # 添加标签
    if node.labels:
        topic["labels"] = node.labels

    return topic


def _sanitize_filename(name: str) -> str:
    """将字符串转换为安全的文件名。

    移除或替换不安全的字符，截断过长的名称。

    Args:
        name: 原始名称。

    Returns:
        安全的文件名字符串。
    """
    # 替换常见的不安全字符
    safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe = safe.replace("*", "").replace("?", "").replace('"', "")
    safe = safe.replace("<", "").replace(">", "").replace("|", "")
    # 截断过长名称
    if len(safe) > 100:
        safe = safe[:100]
    return safe.strip() or "xmind_output"
