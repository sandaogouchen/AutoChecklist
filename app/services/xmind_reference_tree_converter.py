"""将参考 XMind 的 XMindReferenceNode 树确定性转换为 ChecklistNode 树。

转换规则
--------
- 根节点跳过（rootTopic 通常是 checklist 标题）
- 一级子节点 → ChecklistNode(node_type="group", source="reference")
- 中间节点 → ChecklistNode(node_type="group", source="reference")
- 叶子节点 → ChecklistNode(node_type="expected_result", source="reference")
- node_id 生成策略: "ref-" + SHA1(parent_path + "/" + title)[:12]
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from app.domain.checklist_models import ChecklistNode
from app.domain.xmind_reference_models import XMindReferenceNode

logger = logging.getLogger(__name__)


class XMindReferenceTreeConverter:
    """XMindReferenceNode → list[ChecklistNode] 确定性转换器。"""

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def convert(self, root: XMindReferenceNode) -> list[ChecklistNode]:
        """将参考 XMind 的根节点转换为 ChecklistNode 子树列表。

        返回根节点的一级子节点列表（每个是一棵 ChecklistNode 子树），
        跳过 rootTopic 本身。
        """
        if not root.children:
            logger.warning("参考 XMind 根节点无子节点，返回空树")
            return []

        parent_path = root.title or "root"
        return [
            self._convert_node(child, parent_path, depth=1)
            for child in root.children
        ]

    def get_leaf_titles(self, root: XMindReferenceNode) -> list[str]:
        """提取参考树所有叶子节点标题，用于覆盖度检测。"""
        leaves: list[str] = []
        self._collect_leaves(root, leaves)
        return leaves

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _convert_node(
        self,
        node: XMindReferenceNode,
        parent_path: str,
        depth: int,
    ) -> ChecklistNode:
        """递归转换单个节点。"""
        current_path = f"{parent_path}/{node.title}"
        node_id = self._generate_stable_id(parent_path, node.title)

        is_leaf = not node.children
        node_type = "expected_result" if is_leaf else "group"

        children: list[ChecklistNode] = []
        if not is_leaf:
            children = [
                self._convert_node(child, current_path, depth + 1)
                for child in node.children
            ]

        return ChecklistNode(
            node_id=node_id,
            title=node.title,
            node_type=node_type,
            children=children,
            source="reference",
            is_mandatory=False,
        )

    def _collect_leaves(
        self,
        node: XMindReferenceNode,
        acc: list[str],
    ) -> None:
        """递归收集所有叶子标题。"""
        if not node.children:
            if node.title:
                acc.append(node.title)
            return
        for child in node.children:
            self._collect_leaves(child, acc)

    @staticmethod
    def _generate_stable_id(parent_path: str, title: str) -> str:
        """生成稳定的节点 ID: ``ref-`` + SHA1(parent_path/title)[:12]。"""
        raw = f"{parent_path}/{title}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"ref-{digest}"
