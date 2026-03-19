"""Checklist 前置操作合并服务（Trie 算法）。

使用 Trie（前缀树）将共享公共前置操作 / 步骤前缀的测试用例
合并为树形结构 ``list[ChecklistNode]``。

算法流程：
1. 对每个 TestCase，将 ``preconditions + steps`` 拼接为操作序列
2. 对序列中每个元素做归一化（去编号、casefold、统一标点、NFKC）
3. 将归一化后的序列插入 Trie，叶子节点记录原始 TestCase 信息
4. Trie 转换为 ``ChecklistNode`` 树，并做单子节点剪枝
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.domain.checklist_models import ChecklistNode

if TYPE_CHECKING:
    from app.domain.case_models import TestCase

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_MAX_DEPTH = 10  # Trie 最大插入深度，防止异常长序列


# ---------------------------------------------------------------------------
# 内部数据结构
# ---------------------------------------------------------------------------

@dataclass
class _TerminalInfo:
    """​Trie 叶子节点附带的原始 TestCase 信息。"""

    test_case_id: str
    title: str
    remaining_steps: list[str]
    expected_results: list[str]
    priority: str
    category: str
    evidence_refs: list
    checkpoint_id: str


@dataclass
class _TrieNode:
    """Trie 节点。"""

    children: dict[str, _TrieNode] = field(default_factory=dict)
    terminals: list[_TerminalInfo] = field(default_factory=list)
    raw_label: str = ""  # 保留未归一化的原始文本（用于展示）


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------

# 去除序号前缀，如 "1. ", "2) ", "Step 3: "
_NUMBERING_RE = re.compile(
    r"^(?:(?:step\s*)?\d+[\.\)\:\uff1a]\s*)", re.IGNORECASE
)

# 统一中英文标点
_PUNCTUATION_MAP = str.maketrans(
    "\uff0c\u3002\uff1b\uff1a\uff01\uff1f\uff08\uff09\u3010\u3011\u201c\u201d\u2018\u2019",
    ",.;:!?()[]\"\"\\'\\\'"  
)


def _normalize_for_comparison(text: str) -> str:
    """将文本归一化为可比较的规范形式。"""
    text = _NUMBERING_RE.sub("", text)
    text = text.casefold()
    text = text.translate(_PUNCTUATION_MAP)
    text = unicodedata.normalize("NFKC", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 合并器
# ---------------------------------------------------------------------------

class ChecklistMerger:
    """基于 Trie 的 Checklist 前置操作合并器。

    用法::

        merger = ChecklistMerger()
        tree = merger.merge(test_cases)
    """

    def merge(self, test_cases: list[TestCase]) -> list[ChecklistNode]:
        """将测试用例列表合并为 ChecklistNode 树。

        Args:
            test_cases: 输入的测试用例列表。

        Returns:
            合并后的顶层 ChecklistNode 列表。
            如果输入为空，返回空列表。
        """
        if not test_cases:
            return []

        root = _TrieNode()

        for case in test_cases:
            ops = list(case.preconditions) + list(case.steps)
            self._insert(root, ops, case)

        nodes = self._trie_to_nodes(root)
        return self._prune(nodes)

    # ------------------------------------------------------------------
    # Trie 插入
    # ------------------------------------------------------------------

    def _insert(self, root: _TrieNode, ops: list[str], case: TestCase) -> None:
        """将一个 TestCase 的操作序列插入 Trie。"""
        node = root
        depth = 0

        for raw_step in ops:
            if depth >= _MAX_DEPTH:
                break
            key = _normalize_for_comparison(raw_step)
            if not key:
                continue
            if key not in node.children:
                child = _TrieNode(raw_label=raw_step.strip())
                node.children[key] = child
            node = node.children[key]
            depth += 1

        # 剩余步骤 = 超过 Trie 深度的部分
        consumed = min(len(ops), _MAX_DEPTH)
        remaining = [s for s in ops[consumed:] if s.strip()]

        node.terminals.append(
            _TerminalInfo(
                test_case_id=case.id,
                title=case.title,
                remaining_steps=remaining,
                expected_results=list(case.expected_results),
                priority=case.priority,
                category=case.category,
                evidence_refs=list(case.evidence_refs),
                checkpoint_id=case.checkpoint_id,
            )
        )

    # ------------------------------------------------------------------
    # Trie → ChecklistNode 转换
    # ------------------------------------------------------------------

    def _trie_to_nodes(self, trie_node: _TrieNode) -> list[ChecklistNode]:
        """递归将 Trie 转换为 ChecklistNode 列表。"""
        result: list[ChecklistNode] = []

        # 先处理当前节点的 terminals（叶子）
        for term in trie_node.terminals:
            result.append(
                ChecklistNode(
                    node_id=term.test_case_id,
                    title=term.title,
                    node_type="case",
                    test_case_ref=term.test_case_id,
                    remaining_steps=term.remaining_steps,
                    expected_results=term.expected_results,
                    priority=term.priority,
                    category=term.category,
                    evidence_refs=term.evidence_refs,
                    checkpoint_id=term.checkpoint_id,
                )
            )

        # 再处理子节点
        for _key, child in trie_node.children.items():
            child_nodes = self._trie_to_nodes(child)

            if len(child_nodes) == 1 and child_nodes[0].node_type == "case":
                # 只有一个叶子时不创建 group，直接提升
                result.append(child_nodes[0])
            else:
                group = ChecklistNode(
                    node_id=f"GRP-{uuid.uuid4().hex[:8]}",
                    title=child.raw_label,
                    node_type="group",
                    children=child_nodes,
                )
                result.append(group)

        return result

    # ------------------------------------------------------------------
    # 剪枝：消除单子节点 group 链
    # ------------------------------------------------------------------

    def _prune(self, nodes: list[ChecklistNode]) -> list[ChecklistNode]:
        """递归剪除单子节点的 group 链。"""
        pruned: list[ChecklistNode] = []
        for node in nodes:
            pruned.append(self._prune_node(node))
        return pruned

    def _prune_node(self, node: ChecklistNode) -> ChecklistNode:
        """对单个节点做剪枝。"""
        if node.node_type == "case":
            return node

        # 递归剪枝子节点
        pruned_children = [self._prune_node(c) for c in node.children]

        # 如果 group 只有一个子节点且该子节点也是 group，合并标题
        if len(pruned_children) == 1 and pruned_children[0].node_type == "group":
            child = pruned_children[0]
            merged_title = f"{node.title} \u2192 {child.title}" if node.title and child.title else (node.title or child.title)
            return child.model_copy(update={
                "title": merged_title,
                "children": child.children,
            })

        return node.model_copy(update={"children": pruned_children})
