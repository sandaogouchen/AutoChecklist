"""Checkpoint 大纲规划服务。

在 testcase 草稿生成前规划固定层级：
1. 先产出可复用的规范大纲节点
2. 再将每个 checkpoint 映射到固定路径
3. 最后确定性构建共享 ``optimized_tree``
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.checklist_models import (
    CanonicalOutlineNode,
    CanonicalOutlineNodeCollection,
    ChecklistNode,
    CheckpointPathCollection,
    CheckpointPathMapping,
)
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import ResearchOutput
from app.domain.state import CaseGenState

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")

_OUTLINE_SYSTEM_PROMPT = """
You are planning a stable manual-QA checklist hierarchy before testcase drafting.

Stage A responsibilities:
- build canonical reusable outline nodes for the checkpoints below
- hierarchy must be business-object-first
- visible parents are required for core business objects such as Campaign, Ad group,
  Creative, Reporting, TTMS account
- mixed object+state phrases must be split into separate nodes
- no testcase summary nodes
- no "[TC-xxx]" layers
- display_text should be concise and renderable in Markdown/XMind

Allowed node kinds:
- business_object
- context
- page
- action

Visibility rules:
- visible: rendered directly
- required: rendered directly and should not be skipped
- hidden: merge-only anchor, never rendered
""".strip()

_PATH_SYSTEM_PROMPT = """
You are mapping each checkpoint onto a fixed outline path using ONLY the provided
canonical nodes.

Hard constraints:
- every path must include the nearest visible business object
- lifecycle, state, page, and action nodes must sit under that object
- reuse only provided node ids
- do not invent testcase summary layers
- do not generate expected results in this stage

The output must be an ordered path from broad business object to specific operation.
""".strip()


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


@dataclass
class _ResolvedOutlineSegment:
    node_id: str
    display_text: str
    hidden: bool
    kind: str


@dataclass
class _ResolvedCheckpointPath:
    checkpoint_id: str
    path_segments: list[_ResolvedOutlineSegment]


@dataclass
class CheckpointOutlinePlan:
    """规划结果。"""

    canonical_outline_nodes: list[CanonicalOutlineNode]
    checkpoint_paths: list[CheckpointPathMapping]
    optimized_tree: list[ChecklistNode]


@dataclass
class _OutlineTrieNode:
    segment: _ResolvedOutlineSegment | None = None
    children: dict[str, _OutlineTrieNode] = field(default_factory=dict)


class CheckpointOutlinePlanner:
    """将 checkpoint 规划为稳定的共享大纲树。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def plan(
        self,
        research_output: ResearchOutput,
        checkpoints: list[Checkpoint],
    ) -> CheckpointOutlinePlan:
        if not checkpoints:
            return CheckpointOutlinePlan([], [], [])

        facts_payload = [
            {
                "fact_id": fact.fact_id,
                "description": fact.description,
                "category": fact.category,
            }
            for fact in research_output.facts
        ]
        checkpoint_payload = [
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "title": checkpoint.title,
                "objective": checkpoint.objective,
                "category": checkpoint.category,
                "risk": checkpoint.risk,
                "preconditions": checkpoint.preconditions,
                "fact_ids": checkpoint.fact_ids,
            }
            for checkpoint in checkpoints
        ]

        canonical_response = self.llm_client.generate_structured(
            system_prompt=_OUTLINE_SYSTEM_PROMPT,
            user_prompt=(
                "[Facts]\n"
                f"{json.dumps(facts_payload, ensure_ascii=False, indent=2)}\n\n"
                "[Checkpoints]\n"
                f"{json.dumps(checkpoint_payload, ensure_ascii=False, indent=2)}"
            ),
            response_model=CanonicalOutlineNodeCollection,
        )

        path_response = self.llm_client.generate_structured(
            system_prompt=_PATH_SYSTEM_PROMPT,
            user_prompt=self._build_path_prompt(
                checkpoints,
                canonical_response.canonical_nodes,
            ),
            response_model=CheckpointPathCollection,
        )

        resolved_paths = self._resolve_checkpoint_paths(
            checkpoints,
            path_response.checkpoint_paths,
            canonical_response.canonical_nodes,
        )

        return CheckpointOutlinePlan(
            canonical_outline_nodes=canonical_response.canonical_nodes,
            checkpoint_paths=path_response.checkpoint_paths,
            optimized_tree=self._build_outline_tree(resolved_paths),
        )

    def _build_path_prompt(
        self,
        checkpoints: list[Checkpoint],
        canonical_nodes: list[CanonicalOutlineNode],
    ) -> str:
        lines = [
            "[Canonical Nodes]",
            json.dumps(
                {
                    "canonical_nodes": [
                        node.model_dump(mode="json") for node in canonical_nodes
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "[Checkpoint Mapping Inputs]",
        ]

        for checkpoint in checkpoints:
            lines.extend(
                [
                    f"Checkpoint ID: {checkpoint.checkpoint_id}",
                    f"Title: {checkpoint.title}",
                    f"Objective: {checkpoint.objective}",
                    f"Category: {checkpoint.category}",
                    f"Risk: {checkpoint.risk}",
                ]
            )
            if checkpoint.preconditions:
                lines.append("Preconditions:")
                lines.extend(f"- {item}" for item in checkpoint.preconditions)
            if checkpoint.fact_ids:
                lines.append(f"Source facts: {', '.join(checkpoint.fact_ids)}")
            lines.append("")

        return "\n".join(lines).strip()

    def _resolve_checkpoint_paths(
        self,
        checkpoints: list[Checkpoint],
        checkpoint_paths: list[CheckpointPathMapping],
        canonical_nodes: list[CanonicalOutlineNode],
    ) -> list[_ResolvedCheckpointPath]:
        node_lookup = {node.node_id: node for node in canonical_nodes}
        path_lookup = {path.checkpoint_id: path for path in checkpoint_paths}

        resolved: list[_ResolvedCheckpointPath] = []
        for checkpoint in checkpoints:
            mapping = path_lookup.get(checkpoint.checkpoint_id)
            if mapping is None:
                resolved.append(
                    _ResolvedCheckpointPath(
                        checkpoint_id=checkpoint.checkpoint_id,
                        path_segments=self._fallback_segments(checkpoint),
                    )
                )
                continue

            path_segments: list[_ResolvedOutlineSegment] = []
            for node_id in mapping.path_node_ids:
                node = node_lookup.get(node_id)
                if node is None:
                    continue
                path_segments.append(
                    _ResolvedOutlineSegment(
                        node_id=node.node_id,
                        display_text=node.display_text,
                        hidden=node.visibility == "hidden",
                        kind=node.kind,
                    )
                )

            if not path_segments:
                path_segments = self._fallback_segments(checkpoint)

            resolved.append(
                _ResolvedCheckpointPath(
                    checkpoint_id=checkpoint.checkpoint_id,
                    path_segments=path_segments,
                )
            )

        return resolved

    def _fallback_segments(self, checkpoint: Checkpoint) -> list[_ResolvedOutlineSegment]:
        segments: list[_ResolvedOutlineSegment] = []
        for index, text in enumerate([*checkpoint.preconditions, checkpoint.title], start=1):
            normalized = text.strip()
            if not normalized:
                continue
            segments.append(
                _ResolvedOutlineSegment(
                    node_id=f"{checkpoint.checkpoint_id}-fallback-{index}",
                    display_text=normalized,
                    hidden=False,
                    kind="action" if index == len(checkpoint.preconditions) + 1 else "context",
                )
            )
        return segments

    def _build_outline_tree(
        self,
        resolved_paths: list[_ResolvedCheckpointPath],
    ) -> list[ChecklistNode]:
        if not resolved_paths:
            return []

        root = _OutlineTrieNode()
        for resolved_path in resolved_paths:
            cursor = root
            for segment in resolved_path.path_segments:
                segment_key = segment.node_id or _normalize_text(segment.display_text)
                if not segment_key:
                    continue
                child = cursor.children.get(segment_key)
                if child is None:
                    child = _OutlineTrieNode(segment=segment)
                    cursor.children[segment_key] = child
                cursor = child

        return self._build_children(root)

    def _build_children(self, trie_node: _OutlineTrieNode) -> list[ChecklistNode]:
        nodes: list[ChecklistNode] = []
        for child in trie_node.children.values():
            nodes.extend(self._build_node_or_flatten(child))
        return self._merge_siblings(nodes)

    def _build_node_or_flatten(self, trie_node: _OutlineTrieNode) -> list[ChecklistNode]:
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
            )
        ]

    def _merge_siblings(self, nodes: list[ChecklistNode]) -> list[ChecklistNode]:
        merged: dict[tuple[str, str], ChecklistNode] = {}
        order: list[tuple[str, str]] = []

        for node in nodes:
            merge_key = ("group", node.node_id or _normalize_text(node.title))
            existing = merged.get(merge_key)
            if existing is None:
                merged[merge_key] = node.model_copy(deep=True)
                order.append(merge_key)
                continue

            merged[merge_key] = existing.model_copy(
                update={
                    "children": self._merge_siblings(existing.children + node.children),
                }
            )

        return [merged[key] for key in order]


def build_checkpoint_outline_planner_node(llm_client: LLMClient):
    """构建 LangGraph 节点。"""

    planner = CheckpointOutlinePlanner(llm_client)

    def checkpoint_outline_planner_node(state: CaseGenState) -> CaseGenState:
        plan = planner.plan(
            state.get("research_output", ResearchOutput()),
            state.get("checkpoints", []),
        )
        return {
            "canonical_outline_nodes": plan.canonical_outline_nodes,
            "checkpoint_paths": plan.checkpoint_paths,
            "optimized_tree": plan.optimized_tree,
        }

    return checkpoint_outline_planner_node


def attach_expected_results_to_outline(
    optimized_tree: list[ChecklistNode],
    test_cases: list[TestCase],
    checkpoint_paths: list[CheckpointPathMapping] | None = None,
    canonical_outline_nodes: list[CanonicalOutlineNode] | None = None,
) -> list[ChecklistNode]:
    """将 testcase 信息挂载到既有大纲树。

    当提供 ``checkpoint_paths`` 与 ``canonical_outline_nodes`` 时，沿固定层级路径
    把 expected results 挂到叶子 group 节点下；这是当前工作流的主路径。

    当仅提供 ``optimized_tree`` 和 ``test_cases`` 时，回退到对已有 ``case`` 节点
    的原位富化逻辑，以兼容仍在使用旧调用约定的代码和测试。
    """
    if not optimized_tree or not test_cases:
        return optimized_tree

    if checkpoint_paths and canonical_outline_nodes:
        return _attach_expected_results_by_path(
            optimized_tree,
            test_cases,
            checkpoint_paths,
            canonical_outline_nodes,
        )

    return _attach_case_fields_in_place(optimized_tree, test_cases)


def _attach_expected_results_by_path(
    optimized_tree: list[ChecklistNode],
    test_cases: list[TestCase],
    checkpoint_paths: list[CheckpointPathMapping],
    canonical_outline_nodes: list[CanonicalOutlineNode],
) -> list[ChecklistNode]:
    tree = [node.model_copy(deep=True) for node in optimized_tree]
    node_lookup = {node.node_id: node for node in canonical_outline_nodes}
    path_lookup = {path.checkpoint_id: path for path in checkpoint_paths}

    for test_case in test_cases:
        if not test_case.expected_results:
            continue

        mapping = path_lookup.get(test_case.checkpoint_id)
        if mapping is None:
            continue

        visible_path_ids = [
            node_id
            for node_id in mapping.path_node_ids
            if node_lookup.get(node_id) is None
            or node_lookup[node_id].visibility != "hidden"
        ]
        if not visible_path_ids:
            continue

        target = _find_group_node(tree, visible_path_ids)
        if target is None:
            continue

        for expected_result in test_case.expected_results:
            normalized_result = _normalize_text(expected_result)
            if not normalized_result:
                continue

            existing_leaf = next(
                (
                    child
                    for child in target.children
                    if child.node_type == "expected_result"
                    and _normalize_text(child.title) == normalized_result
                ),
                None,
            )
            if existing_leaf is not None:
                existing_leaf.source_test_case_refs = sorted(
                    set(existing_leaf.source_test_case_refs).union({test_case.id})
                )
                continue

            target.children.append(
                ChecklistNode(
                    node_id=_stable_id(
                        "EXP",
                        f"{'|'.join(visible_path_ids)}||{expected_result.strip()}",
                    ),
                    title=expected_result.strip(),
                    node_type="expected_result",
                    source_test_case_refs=[test_case.id],
                )
            )

    return tree


def _attach_case_fields_in_place(
    optimized_tree: list[ChecklistNode],
    test_cases: list[TestCase],
) -> list[ChecklistNode]:
    try:
        cp_to_cases: dict[str, list[TestCase]] = defaultdict(list)
        for tc in test_cases:
            if tc.checkpoint_id:
                cp_to_cases[tc.checkpoint_id].append(tc)

        def _enrich_children(children: list[ChecklistNode]) -> list[ChecklistNode]:
            new_children: list[ChecklistNode] = []
            for node in children:
                if node.children:
                    node.children = _enrich_children(node.children)

                if node.node_type == "case" and node.checkpoint_id:
                    matching = cp_to_cases.get(node.checkpoint_id, [])
                    if not matching:
                        new_children.append(node)
                        continue

                    _fill_node_from_testcase(node, matching[0])
                    new_children.append(node)

                    for extra_tc in matching[1:]:
                        sibling = ChecklistNode(
                            node_id=f"{node.node_id}__tc__{extra_tc.id}",
                            title=extra_tc.title or node.title,
                            node_type="case",
                            children=[],
                            checkpoint_id=node.checkpoint_id,
                        )
                        _fill_node_from_testcase(sibling, extra_tc)
                        new_children.append(sibling)
                else:
                    new_children.append(node)

            return new_children

        return _enrich_children(optimized_tree)
    except Exception:
        logger.warning(
            "attach_expected_results_to_outline failed; returning unmodified tree",
            exc_info=True,
        )
        return optimized_tree


def _fill_node_from_testcase(node: ChecklistNode, tc: TestCase) -> None:
    node.steps = list(tc.steps or [])
    node.preconditions = list(tc.preconditions or [])
    node.expected_results = list(tc.expected_results or [])
    node.priority = tc.priority or "P2"
    node.category = tc.category or "functional"
    node.evidence_refs = list(tc.evidence_refs or [])
    node.test_case_ref = tc.id or ""


def _find_group_node(
    nodes: list[ChecklistNode],
    visible_path_ids: list[str],
) -> ChecklistNode | None:
    current_nodes = nodes
    current_node: ChecklistNode | None = None

    for node_id in visible_path_ids:
        current_node = next(
            (
                node
                for node in current_nodes
                if node.node_type in {"group", "precondition_group"}
                and node.node_id == node_id
            ),
            None,
        )
        if current_node is None:
            return None
        current_nodes = current_node.children

    return current_node
