"""Checklist 前置条件分组优化节点。

作为 LangGraph 子图中的一个节点，在 structure_assembler 之后执行：
1. 从 CaseGenState 读取 test_cases
2. 调用 PreconditionGrouper.group() 构建 optimized_tree
3. 返回增量更新 {test_cases, optimized_tree}

异常安全：任何分组错误仅记录日志，返回空 tree，下游回退到扁平渲染。
"""

from __future__ import annotations

import logging
from typing import Any

from app.config.settings import get_settings
from app.domain.state import CaseGenState
from app.services.precondition_grouper import PreconditionGrouper

logger = logging.getLogger(__name__)


def checklist_optimizer_node(state: CaseGenState) -> dict[str, Any]:
    """将 test_cases 按前置条件分组为 optimized_tree。

    跳过条件：
    - test_cases 为空
    - settings.enable_checklist_optimization 为 False

    异常时返回空 tree，不影响下游。
    """
    test_cases = state.get("test_cases", [])

    if not test_cases:
        return {"test_cases": test_cases, "optimized_tree": []}

    settings = get_settings()
    if not settings.enable_checklist_optimization:
        return {"test_cases": test_cases, "optimized_tree": []}

    try:
        grouper = PreconditionGrouper()
        optimized_tree = grouper.group(test_cases)
    except Exception:
        logger.warning(
            "PreconditionGrouper.group() failed; returning empty tree",
            exc_info=True,
        )
        optimized_tree = []

    return {"test_cases": test_cases, "optimized_tree": optimized_tree}
