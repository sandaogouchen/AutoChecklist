"""项目级 Checklist 模版加载与校验服务。

提供 ``ProjectTemplateLoader`` 类，负责：
- 从 YAML 文件加载模版（支持 mandatory_levels 和 mandatory 字段）
- 校验模版结构完整性（ID 唯一性、至少一个叶子、mandatory_levels 校验等）
- 将模版树拍平为叶子目标集合
- 构建强制骨架树

注意：YAML 解析依赖 ``pyyaml`` 包，如未安装会在加载时抛出 RuntimeError。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.domain.template_models import (
    MandatorySkeletonNode,
    ProjectChecklistTemplateFile,
    ProjectChecklistTemplateMetadata,
    ProjectChecklistTemplateNode,
    TemplateLeafTarget,
)
from app.services.mandatory_skeleton_builder import MandatorySkeletonBuilder

logger = logging.getLogger(__name__)


class TemplateValidationError(ValueError):
    """模版校验失败异常。"""


class ProjectTemplateLoader:
    """项目级 Checklist 模版加载器。

    提供模版文件的加载、校验、拍平和强制骨架构建功能。
    """

    def __init__(self) -> None:
        self._skeleton_builder = MandatorySkeletonBuilder()

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
            import yaml
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

        nodes = [self._parse_node(n) for n in raw_nodes if isinstance(n, dict)]

        template = ProjectChecklistTemplateFile(metadata=metadata, nodes=nodes)
        self.validate_template(template)
        return template

    def load_by_name(self, template_name: str, template_dir: str = "templates") -> ProjectChecklistTemplateFile:
        """按名称从模版目录加载模版。

        Args:
            template_name: 模版名称（不含扩展名）。
            template_dir: 模版目录路径。

        Returns:
            解析后的模版文件对象。

        Raises:
            FileNotFoundError: 模版文件不存在。
        """
        dir_path = Path(template_dir)
        for ext in (".yaml", ".yml"):
            file_path = dir_path / f"{template_name}{ext}"
            if file_path.exists():
                return self.load(file_path)

        raise FileNotFoundError(
            f"Template '{template_name}' not found in {template_dir}/ directory"
        )

    def flatten_leaves(
        self, template: ProjectChecklistTemplateFile
    ) -> list[TemplateLeafTarget]:
        """将模版树拍平为叶子目标集合。"""
        leaves: list[TemplateLeafTarget] = []
        for node in template.nodes:
            self._collect_leaves(node, path_ids=[], path_titles=[], result=leaves)
        return leaves

    def build_mandatory_skeleton(
        self, template: ProjectChecklistTemplateFile
    ) -> MandatorySkeletonNode | None:
        """构建强制骨架树。

        Args:
            template: 模版文件对象。

        Returns:
            强制骨架根节点，无强制约束时返回 None。
        """
        return self._skeleton_builder.build(template)

    def validate_template(self, template: ProjectChecklistTemplateFile) -> None:
        """校验模版结构完整性。

        校验规则：
        1. 至少包含一个节点
        2. 至少包含一个叶子节点
        3. 所有节点 ID 在整棵树中唯一
        4. 所有节点 ID 非空
        5. mandatory_levels 中的层级不超过实际最大深度（仅 Warning）

        Raises:
            TemplateValidationError: 校验失败。
        """
        if not template.nodes:
            raise TemplateValidationError("模版至少需要包含一个节点")

        all_ids: list[str] = []
        leaf_count = 0
        for node in template.nodes:
            self._collect_ids_and_count_leaves(node, all_ids)

        for node in template.nodes:
            leaf_count += self._count_leaves(node)

        if leaf_count == 0:
            raise TemplateValidationError("模版至少需要包含一个叶子节点")

        # 检查空 ID（过滤掉空 ID 节点已在 _parse_node 中处理，这里做兜底）
        for nid in all_ids:
            if not nid or not nid.strip():
                raise TemplateValidationError("模版节点 ID 不能为空")

        # 检查 ID 唯一性
        seen: set[str] = set()
        for nid in all_ids:
            if nid in seen:
                raise TemplateValidationError(f"模版节点 ID 重复: {nid}")
            seen.add(nid)

        # 检查 mandatory_levels 是否超出实际深度（仅 Warning）
        if template.metadata.mandatory_levels:
            max_depth = self._get_max_depth(template.nodes, current_depth=1)
            for level in template.metadata.mandatory_levels:
                if level > max_depth:
                    logger.warning(
                        "mandatory_levels 包含的层级 %d 超过模版实际最大深度 %d，将被忽略",
                        level,
                        max_depth,
                    )

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
        description = raw.get("description", "")
        priority = raw.get("priority", "")
        note = raw.get("note", "")
        status = raw.get("status", "")
        mandatory = bool(raw.get("mandatory", False))
        raw_children = raw.get("children", [])

        children = []
        if isinstance(raw_children, list):
            for c in raw_children:
                if isinstance(c, dict) and c.get("id"):
                    children.append(self._parse_node(c))
                elif isinstance(c, dict) and not c.get("id"):
                    logger.warning("模版节点 ID 为空，已自动过滤: %s", c)

        return ProjectChecklistTemplateNode(
            id=node_id,
            title=title,
            description=description,
            priority=priority,
            note=note,
            status=status,
            mandatory=mandatory,
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

    def _get_max_depth(
        self, nodes: list[ProjectChecklistTemplateNode], current_depth: int
    ) -> int:
        """获取模版树的最大深度。"""
        if not nodes:
            return current_depth - 1
        return max(
            self._get_max_depth(node.children, current_depth + 1)
            if node.children
            else current_depth
            for node in nodes
        )
