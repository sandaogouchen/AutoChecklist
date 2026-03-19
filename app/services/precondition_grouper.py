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
import re
import unicodedata
import uuid
from collections import Counter, OrderedDict
from typing import Sequence

from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_MAX_TREE_DEPTH = 3
_MIN_GROUP_SIZE = 2
_OTHER_GROUP_TITLE = "其他"

_GENERIC_ASCII_TERMS = {
    "create",
    "create ad group",
    "create ad",
    "ad group",
    "create creative",
    "creative",
    "web & app",
    "page",
    "field",
    "user",
    "system",
    "goal",
    "account",
    "app",
    "web",
}

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


def _normalize_keyword_key(text: str) -> str:
    """归一化关键词键，便于跨大小写和空白匹配。"""
    return " ".join(text.split()).casefold()


def _is_generic_ascii_candidate(candidate: str) -> bool:
    """过滤过于通用的英文候选词。"""
    key = _normalize_keyword_key(candidate)
    if not key or key.isdigit():
        return True
    if key in _GENERIC_ASCII_TERMS:
        return True

    words = key.split()
    if len(words) == 1:
        token = words[0]
        if len(token) <= 2 and not token.isupper():
            return True
        if not (token.isupper() or any(ch.isdigit() for ch in token) or "_" in token):
            return True

    if len(words) == 2 and key in {"web &", "& app"}:
        return True
    return False


def _iter_ascii_candidates(text: str) -> list[str]:
    """提取英文/缩写关键词候选。"""
    candidates: list[str] = []
    seen: set[str] = set()

    for raw_segment in re.findall(r"[A-Za-z0-9][A-Za-z0-9_&+/\- ]*[A-Za-z0-9]", text):
        words = re.findall(r"[A-Za-z0-9_&+/\-]+", raw_segment)
        if not words:
            continue

        max_ngram = min(3, len(words))
        for size in range(max_ngram, 1, -1):
            for start in range(len(words) - size + 1):
                phrase = " ".join(words[start:start + size]).strip()
                if _is_generic_ascii_candidate(phrase):
                    continue

                key = _normalize_keyword_key(phrase)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(phrase)

        for token in words:
            if _is_generic_ascii_candidate(token):
                continue
            key = _normalize_keyword_key(token)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(token)

    return candidates


def _extract_keyword_candidates(text: str) -> list[str]:
    """从单条前置条件中提取关键词候选。"""
    normalized = _normalize_precondition(text)
    candidates: list[str] = []
    seen: set[str] = set()

    for phrase in re.findall(r"`([^`]+)`", normalized):
        ascii_candidates = _iter_ascii_candidates(phrase)
        if ascii_candidates:
            phrase_candidates = ascii_candidates
        elif re.search(r"[A-Za-z]", phrase):
            phrase_candidates = [] if _is_generic_ascii_candidate(phrase) else [phrase.strip()]
        else:
            phrase_candidates = [phrase.strip()]

        for candidate in phrase_candidates:
            key = _normalize_keyword_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate.strip())

    for candidate in _iter_ascii_candidates(normalized):
        key = _normalize_keyword_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)

    return candidates


def _keyword_score(keyword: str, frequency: int) -> tuple[int, int, int]:
    """为关键词排序打分。"""
    words = keyword.split()
    return (frequency, len(words), len(keyword))


# ---------------------------------------------------------------------------
# 分组引擎
# ---------------------------------------------------------------------------

class PreconditionGrouper:
    """前置条件分组引擎。

    将 list[TestCase] 按主关键词单归属分组，
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

        buckets = self._bucket_by_keyword(test_cases)
        return self._build_grouped_tree(buckets)

    # ----- 内部方法 -----

    def _bucket_by_keyword(
        self, test_cases: list[TestCase]
    ) -> OrderedDict[str, list[TestCase]]:
        """按主关键词单归属分桶，保持插入顺序。"""
        keyword_display: OrderedDict[str, str] = OrderedDict()
        per_case_candidates: list[set[str]] = []
        frequencies: Counter[str] = Counter()

        for tc in test_cases:
            candidates: set[str] = set()
            for precondition in tc.preconditions:
                for candidate in _extract_keyword_candidates(precondition):
                    key = _normalize_keyword_key(candidate)
                    keyword_display.setdefault(key, candidate)
                    candidates.add(key)
            per_case_candidates.append(candidates)
            frequencies.update(candidates)

        raw_buckets: OrderedDict[str, list[TestCase]] = OrderedDict()
        other_cases: list[TestCase] = []

        for tc, candidate_keys in zip(test_cases, per_case_candidates):
            shared_candidates = [
                key for key in candidate_keys
                if frequencies[key] >= _MIN_GROUP_SIZE
            ]

            if not shared_candidates:
                other_cases.append(tc)
                continue

            primary_keyword = max(
                shared_candidates,
                key=lambda key: _keyword_score(
                    keyword_display.get(key, key), frequencies[key]
                ),
            )
            display = keyword_display.get(primary_keyword, primary_keyword)
            raw_buckets.setdefault(display, []).append(tc)

        buckets: OrderedDict[str, list[TestCase]] = OrderedDict()
        for display, cases in raw_buckets.items():
            if len(cases) < _MIN_GROUP_SIZE:
                other_cases.extend(cases)
                continue
            buckets[display] = cases

        if other_cases and (buckets or len(other_cases) >= _MIN_GROUP_SIZE):
            buckets[_OTHER_GROUP_TITLE] = other_cases
        elif other_cases:
            for tc in other_cases:
                buckets.setdefault(tc.id, []).append(tc)

        return buckets

    def _build_grouped_tree(
        self, buckets: OrderedDict[str, list[TestCase]]
    ) -> list[ChecklistNode]:
        """将分桶结果构建为 ChecklistNode 列表。

        规则：
        - 命中主关键词的桶：创建 precondition_group 节点
        - 未命中共享关键词的用例：收敛到“其他”桶
        - 仅单条、且无任何可分组上下文时：保持独立 case 节点
        """
        children: list[ChecklistNode] = []

        for key, cases in buckets.items():
            if key == _OTHER_GROUP_TITLE:
                group_node = self._build_precondition_group(key, cases)
                children.append(group_node)
                continue

            if len(cases) < _MIN_GROUP_SIZE:
                # 不分组，每条用例直接作为 case 节点
                for tc in cases:
                    children.append(self._build_case_node(tc))
                continue

            # 创建分组节点
            group_node = self._build_precondition_group(key, cases)
            children.append(group_node)

        return children

    def _build_precondition_group(
        self,
        keyword: str,
        cases: list[TestCase],
    ) -> ChecklistNode:
        """构建一个关键词分组节点。"""
        group_title = keyword
        group_id = f"GRP-{uuid.uuid4().hex[:8]}"

        case_children = [
            self._build_case_node(tc)
            for tc in cases
        ]

        return ChecklistNode(
            node_id=group_id,
            title=group_title,
            node_type="precondition_group",
            children=case_children,
            preconditions=[],
        )

    def _build_case_node(
        self,
        tc: TestCase,
    ) -> ChecklistNode:
        """构建一个 case 叶子节点。

        关键词分组模式下，case 节点保留完整前置条件。
        """
        return ChecklistNode(
            node_id=f"CASE-{tc.id}",
            title=tc.title,
            node_type="case",
            test_case_ref=tc.id,
            preconditions=list(tc.preconditions),
            steps=list(tc.steps),
            expected_results=list(tc.expected_results),
            priority=tc.priority,
            category=tc.category,
            evidence_refs=list(tc.evidence_refs),
            checkpoint_id=tc.checkpoint_id,
        )
