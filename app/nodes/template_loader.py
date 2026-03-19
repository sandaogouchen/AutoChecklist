"""模版加载工作流节点。

在主工作流中负责加载项目级 Checklist 模版文件，
将解析后的模版数据写入工作流状态，供下游节点使用。

当 ``template_file_path`` 为空或 None 时，节点自动跳过，
保持向后兼容。
"""

from __future__ import annotations

import logging

from app.domain.state import GlobalState
from app.services.template_loader import ProjectTemplateLoader

logger = logging.getLogger(__name__)


def build_template_loader_node():
    """构建模版加载节点的工厂函数。

    Returns:
        模版加载节点函数，签名为 ``(GlobalState) -> GlobalState``。
    """
    loader = ProjectTemplateLoader()

    def template_loader_node(state: GlobalState) -> GlobalState:
        """从工作流状态中读取模版文件路径并加载模版。

        如果 ``template_file_path`` 为空或 None，则跳过加载，
        返回空的模版数据，保持向后兼容。

        Returns:
            包含 ``project_template`` 和 ``template_leaf_targets`` 的状态增量。
        """
        # 优先从 state 直接获取，其次从 request 对象获取
        template_file_path = state.get("template_file_path", "")
        if not template_file_path:
            request = state.get("request")
            if request is not None:
                template_file_path = getattr(request, "template_file_path", None) or ""

        if not template_file_path:
            logger.debug("未提供模版文件路径，跳过模版加载")
            return {}

        logger.info("加载项目级 Checklist 模版: %s", template_file_path)

        template = loader.load(template_file_path)
        leaf_targets = loader.flatten_leaves(template)

        logger.info(
            "模版加载完成: %s, 叶子节点数: %d",
            template.metadata.name or template_file_path,
            len(leaf_targets),
        )

        return {
            "project_template": template,
            "template_leaf_targets": leaf_targets,
        }

    return template_loader_node
