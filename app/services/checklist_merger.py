"""Checklist 共享逻辑树合并服务。

消费 LLM 归一化后的语义路径，将多条测试用例合并为一棵共享前缀树：

- 中间节点只保留共享前置/操作逻辑（``group``）
- 叶子节点只保留预期结果（``expected_result``）
- 隐藏语义锚点仅用于合并，不直接展示在最终树中
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.domain.checklist_models import ChecklistNode
from app.services.semantic_path_normalizer import (
    NormalizedChecklistPath,
    NormalizedPathSegment,
)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    """压缩空白并做 casefold，供去重使用。"""
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def _stable_id(prefix: str, value: str) -> str:
    """为节点生成稳定 ID。"""
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


@dataclass
class _ExpectedResultBucket:
    """同一路径下的去重预期结果。"""

    title: str
    source_test_case_refs: set[str] = field(default_factory=set)


@dataclass
class _TrieNode:
    """语义路径前缀树节点。"""

    segment: NormalizedPathSegment | None = None
    children: dict[str, _TrieNode] = field(default_factory=dict)
    expected_results: dict[str, _ExpectedResultBucket] = field(default_factory=dict)
    source_test_case_refs: set[str] = field(default_factory=set)


class ChecklistMerger:
    """将归一化语义路径合并成共享 Checklist 树。"""

    def merge(
        self,
        normalized_paths: list[NormalizedChecklistPath],
    ) -> list[ChecklistNode]:
        """合并语义路径。

        Args:
            normalized_paths: LLM 归一化后的测试路径。

        Returns:
            仅包含 ``group`` 和 ``expected_result`` 节点的树。
        """
        if not normalized_paths:
            return []

        root = _TrieNode()
        for normalized_path in normalized_paths:
            self._insert(root, normalized_path)

        return self._build_children(root)

    def _insert(self, root: _TrieNode, normalized_path: NormalizedChecklistPath) -> None:
        """将单条语义路径插入前缀树。"""
        node = root
        node.source_test_case_refs.add(normalized_path.test_case_id)

        for segment in normalized_path.path_segments:
            segment_key = segment.node_id or _normalize_text(segment.display_text)
            if not segment_key:
                continue

            child = node.children.get(segment_key)
            if child is None:
                child = _TrieNode(segment=segment)
                node.children[segment_key] = child

            child.source_test_case_refs.add(normalized_path.test_case_id)
            node = child

        for expected_result in normalized_path.expected_results:
            normalized_result = _normalize_text(expected_result)
            if not normalized_result:
                continue

            bucket = node.expected_results.get(normalized_result)
            if bucket is None:
                bucket = _ExpectedResultBucket(title=expected_result.strip())
                node.expected_results[normalized_result] = bucket

            bucket.source_test_case_refs.add(normalized_path.test_case_id)

    def _build_children(self, trie_node: _TrieNode) -> list[ChecklistNode]:
        """将 Trie 子树转换为 ChecklistNode 列表。"""
        nodes: list[ChecklistNode] = []

        for child in trie_node.children.values():
            nodes.extend(self._build_node_or_flatten(child))

        for normalized_result, bucket in trie_node.expected_results.items():
            nodes.append(
                ChecklistNode(
                    node_id=_stable_id("EXP", normalized_result),
                    title=bucket.title,
                    node_type="expected_result",
                    source_test_case_refs=sorted(bucket.source_test_case_refs),
                )
            )

        return self._merge_siblings(nodes)

    def _build_node_or_flatten(self, trie_node: _TrieNode) -> list[ChecklistNode]:
        """构建可见 group，或在隐藏锚点时直接提升其后代。"""
        children = self._build_children(trie_node)
        segment = trie_node.segment

        if segment is None or segment.hidden:
            return children

        return [
            ChecklistNode(
                node_id=segment.node_id,
                title=segment.display_text,
                node_type="group",
                hidden=False,
                children=children,
                source_test_case_refs=sorted(trie_node.source_test_case_refs),
            )
        ]

    def _merge_siblings(self, nodes: list[ChecklistNode]) -> list[ChecklistNode]:
        """合并因隐藏锚点折叠产生的同级重复节点。"""
        merged: dict[tuple[str, str], ChecklistNode] = {}
        order: list[tuple[str, str]] = []

        for node in nodes:
            merge_key = self._node_merge_key(node)
            existing = merged.get(merge_key)

            if existing is None:
                merged[merge_key] = node.model_copy(deep=True)
                order.append(merge_key)
                continue

            merged[merge_key] = self._merge_node_pair(existing, node)

        return [merged[key] for key in order]

    def _merge_node_pair(
        self,
        left: ChecklistNode,
        right: ChecklistNode,
    ) -> ChecklistNode:
        """合并两个语义相同的节点。"""
        combined_refs = sorted(
            set(left.source_test_case_refs).union(right.source_test_case_refs)
        )

        if left.node_type == "group" and right.node_type == "group":
            combined_children = self._merge_siblings(left.children + right.children)
            return left.model_copy(
                update={
                    "children": combined_children,
                    "source_test_case_refs": combined_refs,
                }
            )

        return left.model_copy(update={"source_test_case_refs": combined_refs})

    def _node_merge_key(self, node: ChecklistNode) -> tuple[str, str]:
        """返回节点的合并键。"""
        if node.node_type == "group":
            return ("group", node.node_id or _normalize_text(node.title))
        if node.node_type == "expected_result":
            return ("expected_result", _normalize_text(node.title))
        return (node.node_type, node.node_id or _normalize_text(node.title))
