"""模版加载工作流节点。

在主工作流中负责加载项目级 Checklist 模版文件，
将解析后的模版数据写入工作流状态，供下游节点使用。

当 ``template_file_path`` 和 ``template_name`` 均为空时，节点自动跳过。

新增强制骨架构建：加载模版后自动构建 mandatory_skeleton。
"""

from __future__ import annotations

import logging

from app.domain.state import GlobalState
from app.services.template_loader import ProjectTemplateLoader

logger = logging.getLogger(__name__)


def build_template_loader_node():
    """构建模版加载节点的工厂函数。"""
    loader = ProjectTemplateLoader()

    def template_loader_node(state: GlobalState) -> GlobalState:
        """从工作流状态中读取模版文件路径或名称并加载模版。"""
        # 优先从 state 直接获取，其次从 request 对象获取
        template_file_path = state.get("template_file_path", "")
        template_name = None

        if not template_file_path:
            request = state.get("request")
            if request is not None:
                template_file_path = getattr(request, "template_file_path", None) or ""
                template_name = getattr(request, "template_name", None) or ""

        if not template_file_path and not template_name:
            logger.debug("未提供模版文件路径或名称，跳过模版加载")
            return {}

        logger.info(
            "加载项目级 Checklist 模版: path=%s, name=%s",
            template_file_path or "-",
            template_name or "-",
        )

        # 优先使用 template_name（从 templates/ 目录加载）
        if template_name:
            template = loader.load_by_name(template_name)
        else:
            template = loader.load(template_file_path)

        leaf_targets = loader.flatten_leaves(template)
        mandatory_skeleton = loader.build_mandatory_skeleton(template)

        logger.info(
            "模版加载完成: %s, 叶子节点数: %d, 强制骨架: %s",
            template.metadata.name or template_file_path or template_name,
            len(leaf_targets),
            "已构建" if mandatory_skeleton else "无",
        )

        result: dict = {
            "project_template": template,
            "template_leaf_targets": leaf_targets,
        }

        if mandatory_skeleton is not None:
            result["mandatory_skeleton"] = mandatory_skeleton

        return result

    return template_loader_node
