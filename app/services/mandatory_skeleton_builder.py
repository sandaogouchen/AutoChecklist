"""强制骨架构建器。

从 Checklist 模版中提取强制节点，构建强制骨架树（Mandatory Skeleton）。
强制骨架作为 outline 规划和 case 挂载的硬约束输入。

强制性判定规则：
1. 节点所在层级 ∈ mandatory_levels → 强制
2. 节点 mandatory == True → 强制
3. 强制层级内的所有后代节点自动继承强制性（直到超出 mandatory_levels 范围）
"""

from __future__ import annotations

import logging

from app.domain.template_models import (
    MandatorySkeletonNode,
    ProjectChecklistTemplateFile,
    ProjectChecklistTemplateNode,
)

logger = logging.getLogger(__name__)


class MandatorySkeletonBuilder:
    """从模版构建强制骨架树。"""

    def build(
        self, template: ProjectChecklistTemplateFile
    ) -> MandatorySkeletonNode | None:
        """从模版构建强制骨架。

        Args:
            template: 完整的模版文件对象。

        Returns:
            强制骨架根节点，如果模版无强制约束则返回 None。
        """
        mandatory_levels = set(template.metadata.mandatory_levels)

        # 如果没有 mandatory_levels 且没有任何 mandatory: true 节点，返回 None
        if not mandatory_levels and not self._has_any_mandatory_node(template.nodes):
            logger.debug("模版无强制约束，跳过骨架构建")
            return None

        children: list[MandatorySkeletonNode] = []
        for node in template.nodes:
            skeleton_node = self._build_node(node, depth=1, mandatory_levels=mandatory_levels)
            if skeleton_node is not None:
                children.append(skeleton_node)

        if not children:
            logger.debug("模版无有效强制节点，跳过骨架构建")
            return None

        # 构建虚拟根节点
        root = MandatorySkeletonNode(
            id="__mandatory_root__",
            title="Mandatory Skeleton Root",
            depth=0,
            is_mandatory=True,
            children=children,
        )

        total = self._count_mandatory_nodes(root)
        logger.info(
            "强制骨架构建完成: mandatory_levels=%s, 强制节点总数=%d",
            sorted(mandatory_levels),
            total,
        )
        return root

    def _build_node(
        self,
        node: ProjectChecklistTemplateNode,
        depth: int,
        mandatory_levels: set[int],
    ) -> MandatorySkeletonNode | None:
        """递归构建骨架节点。

        一个节点被纳入骨架的条件（满足任一）：
        1. 其 depth ∈ mandatory_levels
        2. 其 mandatory == True
        3. 其后代中包含强制节点（作为连接路径保留）
        """
        is_level_mandatory = depth in mandatory_levels
        is_node_mandatory = node.mandatory
        is_mandatory = is_level_mandatory or is_node_mandatory

        # 递归处理子节点
        skeleton_children: list[MandatorySkeletonNode] = []
        for child in node.children:
            child_skeleton = self._build_node(
                child, depth=depth + 1, mandatory_levels=mandatory_levels
            )
            if child_skeleton is not None:
                skeleton_children.append(child_skeleton)

        # 如果当前节点不是强制的，也没有强制子节点，则不纳入骨架
        if not is_mandatory and not skeleton_children:
            return None

        original_metadata = {}
        if node.priority:
            original_metadata["priority"] = node.priority
        if node.note:
            original_metadata["note"] = node.note
        if node.status:
            original_metadata["status"] = node.status
        if node.description:
            original_metadata["description"] = node.description

        return MandatorySkeletonNode(
            id=node.id,
            title=node.title,
            depth=depth,
            is_mandatory=is_mandatory,
            original_metadata=original_metadata,
            children=skeleton_children,
        )

    def _has_any_mandatory_node(
        self, nodes: list[ProjectChecklistTemplateNode]
    ) -> bool:
        """检查节点树中是否有任何 mandatory: true 的节点。"""
        for node in nodes:
            if node.mandatory:
                return True
            if self._has_any_mandatory_node(node.children):
                return True
        return False

    def _count_mandatory_nodes(self, node: MandatorySkeletonNode) -> int:
        """统计骨架中的强制节点数量。"""
        count = 1 if node.is_mandatory else 0
        for child in node.children:
            count += self._count_mandatory_nodes(child)
        return count
