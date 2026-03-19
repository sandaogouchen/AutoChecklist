"""前置条件分组引擎。

核心算法：
1. 对每条 TestCase 的 preconditions 做轻量规范化（strip + NFKC + 标点映射）
2. 以规范化后的 precondition tuple 作为分桶键
3. 同键用例合并为一个 precondition_group 节点
4. 构建 ≤3 层 ChecklistNode 树: root → precondition_group → case

设计约束：
- _MIN_GROUP_SIZE = 2：单条用例不创建分组，直接挂根节点
- _MAX_TREE_DEPTH = 3：仅支持三层结构
- 纯函数，无副作用，无 LLM 调用
"""

from __future__ import annotations

import logging
import unicodedata
import uuid
from collections import OrderedDict
from typing import Sequence

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_MAX_TREE_DEPTH = 3
_MIN_GROUP_SIZE = 2

# 中文标点 → 英文标点映射表
_PUNCT_MAP = str.maketrans(
    {
        "\uff0c": ",",   # ，
        "\u3002": ".",   # 。
        "\uff1b": ";",   # ；
        "\uff1a": ":",   # ：
        "\uff08": "(",   # （
        "\uff09": ")",   # ）
        "\u3001": ",",   # 、
        "\uff01": "!",   # ！
        "\uff1f": "?",   # ？
    }
)


# ---------------------------------------------------------------------------
# 规范化工具函数
# ---------------------------------------------------------------------------

def _normalize_precondition(text: str) -> str:
    """对单条前置条件做轻量规范化。

    步骤：
    1. strip 首尾空白
    2. NFKC 统一 Unicode 表示
    3. 中文标点 → 英文标点
    不做 casefold（中文无大小写），不做编号移除。
    """
    result = text.strip()
    result = unicodedata.normalize("NFKC", result)
    result = result.translate(_PUNCT_MAP)
    return result


def _normalize_precondition_list(preconditions: Sequence[str]) -> tuple[str, ...]:
    """将前置条件列表规范化为排序后的 tuple，用作分桶键。"""
    return tuple(sorted(_normalize_precondition(p) for p in preconditions))


def _longest_common_prefix(strings: Sequence[str]) -> str:
    """求多个字符串的最长公共前缀（用于生成分组标题的候选）。"""
    if not strings:
        return ""
    shortest = min(strings, key=len)
    for i, ch in enumerate(shortest):
        if any(s[i] != ch for s in strings):
            return shortest[:i]
    return shortest


# ---------------------------------------------------------------------------
# 分组引擎
# ---------------------------------------------------------------------------

class PreconditionGrouper:
    """前置条件分组引擎。

    将 list[TestCase] 按 preconditions 相同性分组，
    返回 list[ChecklistNode]（根节点的 children）。
    """

    def group(self, test_cases: list[TestCase]) -> list[ChecklistNode]:
        """执行分组，返回根节点的子节点列表。

        Args:
            test_cases: 待分组的测试用例列表。

        Returns:
            ChecklistNode 列表，可直接作为根节点的 children。
            若输入为空，返回空列表。
        """
        if not test_cases:
            return []

        buckets = self._bucket_by_preconditions(test_cases)
        return self._build_grouped_tree(buckets)

    # ----- 内部方法 -----

    def _bucket_by_preconditions(
        self, test_cases: list[TestCase]
    ) -> OrderedDict[tuple[str, ...], list[TestCase]]:
        """按规范化后的 precondition tuple 分桶，保持插入顺序。"""
        buckets: OrderedDict[tuple[str, ...], list[TestCase]] = OrderedDict()
        for tc in test_cases:
            key = _normalize_precondition_list(tc.preconditions)
            buckets.setdefault(key, []).append(tc)
        return buckets

    def _build_grouped_tree(
        self, buckets: OrderedDict[tuple[str, ...], list[TestCase]]
    ) -> list[ChecklistNode]:
        """将分桶结果构建为 ChecklistNode 列表。

        规则：
        - 桶内用例数 < _MIN_GROUP_SIZE：每条用例作为独立 case 节点
        - 桶内用例数 ≥ _MIN_GROUP_SIZE：创建 precondition_group 节点
        - 空前置条件桶：用例作为独立 case 节点（不创建分组）
        """
        children: list[ChecklistNode] = []

        for key, cases in buckets.items():
            if not key or len(cases) < _MIN_GROUP_SIZE:
                # 不分组，每条用例直接作为 case 节点
                for tc in cases:
                    children.append(self._build_case_node(tc, shared_preconditions=()))
                continue

            # 创建分组节点
            group_node = self._build_precondition_group(key, cases)
            children.append(group_node)

        return children

    def _build_precondition_group(
        self,
        precondition_key: tuple[str, ...],
        cases: list[TestCase],
    ) -> ChecklistNode:
        """构建一个 precondition_group 节点。"""
        group_title = " \u2192 ".join(precondition_key)
        group_id = f"GRP-{uuid.uuid4().hex[:8]}"

        case_children = [
            self._build_case_node(tc, shared_preconditions=precondition_key)
            for tc in cases
        ]

        return ChecklistNode(
            node_id=group_id,
            title=group_title,
            node_type="precondition_group",
            children=case_children,
            preconditions=list(precondition_key),
        )

    def _build_case_node(
        self,
        tc: TestCase,
        shared_preconditions: tuple[str, ...] = (),
    ) -> ChecklistNode:
        """构建一个 case 叶子节点。

        如果存在 shared_preconditions，则 case 节点的 preconditions 字段
        仅包含"附加前置条件"（即不在 shared 集合中的条件）。
        """
        shared_set = set(shared_preconditions)
        # 计算附加前置条件：原始条件规范化后不在 shared 中的
        additional = []
        for p in tc.preconditions:
            normalized = _normalize_precondition(p)
            if normalized not in shared_set:
                additional.append(p)  # 保留原始文本

        return ChecklistNode(
            node_id=f"CASE-{tc.id}",
            title=tc.title,
            node_type="case",
            test_case_ref=tc.id,
            preconditions=additional,
            steps=list(tc.steps),
            expected_results=list(tc.expected_results),
            priority=tc.priority,
            category=tc.category,
            evidence_refs=list(tc.evidence_refs),
            checkpoint_id=tc.checkpoint_id,
        )
