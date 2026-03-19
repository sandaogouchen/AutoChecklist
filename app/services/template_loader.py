"""项目级 Checklist 模版加载与校验服务。

提供 ``ProjectTemplateLoader`` 类，负责：
- 从 YAML 文件加载模版
- 校验模版结构完整性（ID 唯一性、至少一个叶子等）
- 将模版树拍平为叶子目标集合

注意：YAML 解析依赖 ``pyyaml`` 包，如未安装会在加载时抛出 RuntimeError。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.domain.template_models import (
    ProjectChecklistTemplateFile,
    ProjectChecklistTemplateMetadata,
    ProjectChecklistTemplateNode,
    TemplateLeafTarget,
)

logger = logging.getLogger(__name__)


class TemplateValidationError(ValueError):
    """模版校验失败异常。"""


class ProjectTemplateLoader:
    """项目级 Checklist 模版加载器。

    提供模版文件的加载、校验和拍平功能。
    """

    def load(self, file_path: str | Path) -> ProjectChecklistTemplateFile:
        """从 YAML 文件加载模版。

        Args:
            file_path: YAML 模版文件路径。

        Returns:
            解析后的模版文件对象。

        Raises:
            RuntimeError: 未安装 pyyaml。
            FileNotFoundError: 模版文件不存在。
            TemplateValidationError: 模版内容格式无效。
        """
        try:
            import yaml  # noqa: F811
        except ImportError:
            raise RuntimeError(
                "pyyaml is required for template loading. "
                "Install it with: pip install pyyaml"
            )

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"模版文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise TemplateValidationError(
                f"模版文件顶层结构必须是字典，实际类型: {type(raw).__name__}"
            )

        # 解析 metadata
        raw_metadata = raw.get("metadata", {})
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}
        metadata = ProjectChecklistTemplateMetadata(**raw_metadata)

        # 解析 nodes
        raw_nodes = raw.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise TemplateValidationError("模版 nodes 字段必须是列表")

        nodes = [self._parse_node(n) for n in raw_nodes]

        template = ProjectChecklistTemplateFile(metadata=metadata, nodes=nodes)
        self.validate_template(template)
        return template

    def flatten_leaves(
        self, template: ProjectChecklistTemplateFile
    ) -> list[TemplateLeafTarget]:
        """将模版树拍平为叶子目标集合。

        遍历整棵模版树，收集所有叶子节点（无 children 的节点），
        并记录从根到叶子的完整路径。

        Args:
            template: 模版文件对象。

        Returns:
            叶子目标列表。
        """
        leaves: list[TemplateLeafTarget] = []
        for node in template.nodes:
            self._collect_leaves(node, path_ids=[], path_titles=[], result=leaves)
        return leaves

    def validate_template(self, template: ProjectChecklistTemplateFile) -> None:
        """校验模版结构完整性。

        校验规则：
        1. 至少包含一个节点
        2. 至少包含一个叶子节点
        3. 所有节点 ID 在整棵树中唯一
        4. 所有节点 ID 非空

        Args:
            template: 待校验的模版文件对象。

        Raises:
            TemplateValidationError: 校验失败。
        """
        if not template.nodes:
            raise TemplateValidationError("模版至少需要包含一个节点")

        all_ids: list[str] = []
        leaf_count = 0
        for node in template.nodes:
            self._collect_ids_and_count_leaves(node, all_ids)

        # 统计叶子数量
        for node in template.nodes:
            leaf_count += self._count_leaves(node)

        if leaf_count == 0:
            raise TemplateValidationError("模版至少需要包含一个叶子节点")

        # 检查空 ID
        for nid in all_ids:
            if not nid or not nid.strip():
                raise TemplateValidationError("模版节点 ID 不能为空")

        # 检查 ID 唯一性
        seen: set[str] = set()
        for nid in all_ids:
            if nid in seen:
                raise TemplateValidationError(f"模版节点 ID 重复: {nid}")
            seen.add(nid)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _parse_node(self, raw: dict) -> ProjectChecklistTemplateNode:
        """递归解析单个模版节点。"""
        if not isinstance(raw, dict):
            raise TemplateValidationError(
                f"模版节点必须是字典，实际类型: {type(raw).__name__}"
            )

        node_id = raw.get("id", "")
        title = raw.get("title", "")
        raw_children = raw.get("children", [])

        children = []
        if isinstance(raw_children, list):
            children = [self._parse_node(c) for c in raw_children]

        return ProjectChecklistTemplateNode(
            id=node_id,
            title=title,
            children=children,
        )

    def _collect_leaves(
        self,
        node: ProjectChecklistTemplateNode,
        path_ids: list[str],
        path_titles: list[str],
        result: list[TemplateLeafTarget],
    ) -> None:
        """递归收集叶子节点。"""
        current_path_ids = path_ids + [node.id]
        current_path_titles = path_titles + [node.title]

        if not node.children:
            # 叶子节点
            result.append(
                TemplateLeafTarget(
                    leaf_id=node.id,
                    leaf_title=node.title,
                    path_ids=current_path_ids,
                    path_titles=current_path_titles,
                    path_text=" > ".join(current_path_titles),
                )
            )
        else:
            for child in node.children:
                self._collect_leaves(child, current_path_ids, current_path_titles, result)

    def _collect_ids_and_count_leaves(
        self,
        node: ProjectChecklistTemplateNode,
        all_ids: list[str],
    ) -> None:
        """递归收集所有节点 ID。"""
        all_ids.append(node.id)
        for child in node.children:
            self._collect_ids_and_count_leaves(child, all_ids)

    def _count_leaves(self, node: ProjectChecklistTemplateNode) -> int:
        """递归统计叶子节点数量。"""
        if not node.children:
            return 1
        return sum(self._count_leaves(c) for c in node.children)
