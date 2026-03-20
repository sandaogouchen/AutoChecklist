"""Checkpoint 大纲规划服务。

在 testcase 草稿生成前规划固定层级：
1. 先产出可复用的规范大纲节点
2. 再将每个 checkpoint 映射到固定路径
3. 最后确定性构建共享 ``optimized_tree``
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

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

# ---------------------------------------------------------------------------
# System prompt for canonical outline planning
# ---------------------------------------------------------------------------

_OUTLINE_SYSTEM_PROMPT = """\
You are an expert QA architect. Given a set of checkpoints that describe \
test scenarios for an advertising platform, produce a canonical outline \
(a tree of reusable path segments) that organizes these checkpoints into \
a fixed hierarchy.

Each node in the outline has:
- id: a short unique identifier (snake_case)
- display_text: human-readable label shown in the checklist
- node_type: one of "page", "action", "context", "business_object", "case", "expected_result"
- children: list of child nodes (may be empty for leaf nodes)

Rules:
1. The tree should have at most 5 levels of depth.
2. Leaf nodes should be of type "case" or "expected_result".
3. Group related checkpoints under shared parent nodes to minimize duplication.
4. Use consistent naming conventions across sibling nodes.
5. Each checkpoint must appear exactly once in the tree as a leaf node.

IMPORTANT: display_text formatting rules
- Each display_text MUST begin with a Chinese action verb (操作动词).
- Use verb-object structure (动宾结构) instead of plain noun phrases.
- Keep UI element names, field names, and proper nouns in English wrapped in backticks.
- Verb selection by node kind:
  * page → use 进入/打开 (e.g., "进入 `Create ad group` 页面")
  * action → use specific verbs like 配置/选择/设置/输入/点击 (e.g., "配置 `Placements` 包含 `TikTok`")
  * context → use 确认/确保/满足 (e.g., "确认当前账号满足白名单条件")
  * business_object → use 定位到/聚焦 (e.g., "定位到 `Optimization goal` 区域")
- Parent-to-child nodes should form a coherent operation sequence.
- Do NOT use bare noun phrases like "Objective = VideoView". Instead use "选择 `Objective` 为 `VideoView`".

Examples:
  ✗ "Objective = VideoView"           → ✓ "选择 `Objective` 为 `VideoView`"
  ✗ "Placements include TikTok"       → ✓ "配置 `Placements` 包含 `TikTok`"
  ✗ "Advertiser whitelist hit"        → ✓ "验证 `Advertiser` 命中白名单"
  ✗ "Create ad group page"            → ✓ "进入 `Create ad group` 页面"
  ✗ "Optimization goal area"          → ✓ "定位到 `Optimization goal` 区域"

Output the outline as a JSON array of root nodes.
"""

_PATH_SYSTEM_PROMPT = """\
You are an expert QA architect. Given a canonical outline (tree of reusable \
path segments) and a list of checkpoints, map each checkpoint to a path in \
the outline tree.

For each checkpoint, produce:
- checkpoint_id: the checkpoint's unique identifier
- path: list of node IDs from root to the leaf node where this checkpoint belongs

Output a JSON array of checkpoint-path mappings.
"""

# ---------------------------------------------------------------------------
# Helper: deterministic hash for deduplication
# ---------------------------------------------------------------------------


def _stable_hash(text: str) -> str:
    """Return a short deterministic hash for *text*."""
    return hashlib.sha256(_WHITESPACE_RE.sub(" ", text.strip()).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Dataclass for internal outline node (before conversion to ChecklistNode)
# ---------------------------------------------------------------------------


@dataclass
class _InternalNode:
    """Lightweight mutable node used during tree construction."""

    id: str
    display_text: str
    node_type: str
    children: list[_InternalNode] = field(default_factory=list)
    checkpoint_id: str | None = None


# ---------------------------------------------------------------------------
# Main planner class
# ---------------------------------------------------------------------------


class CheckpointOutlinePlanner:
    """Plan a checkpoint outline and build an optimized checklist tree.

    Usage::

        planner = CheckpointOutlinePlanner(llm_client)
        outline_nodes = await planner.plan_outline(checkpoints, research)
        path_mappings = await planner.map_checkpoints(outline_nodes, checkpoints)
        tree = planner.build_optimized_tree(outline_nodes, path_mappings, checkpoints)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Step 1: Plan canonical outline
    # ------------------------------------------------------------------

    async def plan_outline(
        self,
        checkpoints: Sequence[Checkpoint],
        research: ResearchOutput,
    ) -> CanonicalOutlineNodeCollection:
        """Ask the LLM to produce a canonical outline for *checkpoints*."""
        checkpoint_summaries = [
            {"id": cp.id, "title": cp.title, "description": cp.description}
            for cp in checkpoints
        ]
        user_msg = (
            "Checkpoints:\n"
            + json.dumps(checkpoint_summaries, ensure_ascii=False, indent=2)
            + "\n\nResearch context:\n"
            + (research.summary if research else "N/A")
        )

        response = await self._llm.chat(
            system=_OUTLINE_SYSTEM_PROMPT,
            user=user_msg,
            response_format="json",
        )

        raw_nodes = json.loads(response)
        nodes = [self._parse_outline_node(n) for n in raw_nodes]
        return CanonicalOutlineNodeCollection(nodes=nodes)

    # ------------------------------------------------------------------
    # Step 2: Map checkpoints → outline paths
    # ------------------------------------------------------------------

    async def map_checkpoints(
        self,
        outline: CanonicalOutlineNodeCollection,
        checkpoints: Sequence[Checkpoint],
    ) -> CheckpointPathCollection:
        """Ask the LLM to map each checkpoint to a path in *outline*."""
        outline_json = json.dumps(
            [self._outline_node_to_dict(n) for n in outline.nodes],
            ensure_ascii=False,
            indent=2,
        )
        checkpoint_summaries = json.dumps(
            [{"id": cp.id, "title": cp.title} for cp in checkpoints],
            ensure_ascii=False,
            indent=2,
        )
        user_msg = (
            "Outline:\n" + outline_json + "\n\nCheckpoints:\n" + checkpoint_summaries
        )

        response = await self._llm.chat(
            system=_PATH_SYSTEM_PROMPT,
            user=user_msg,
            response_format="json",
        )

        raw_mappings = json.loads(response)
        mappings = [
            CheckpointPathMapping(
                checkpoint_id=m["checkpoint_id"],
                path=m["path"],
            )
            for m in raw_mappings
        ]
        return CheckpointPathCollection(mappings=mappings)

    # ------------------------------------------------------------------
    # Step 3: Build optimized tree
    # ------------------------------------------------------------------

    def build_optimized_tree(
        self,
        outline: CanonicalOutlineNodeCollection,
        path_collection: CheckpointPathCollection,
        checkpoints: Sequence[Checkpoint],
    ) -> list[ChecklistNode]:
        """Deterministically build a ``ChecklistNode`` tree.

        Merges identical paths so shared segments are represented once.
        """
        # Build lookup: checkpoint_id → Checkpoint
        cp_lookup: dict[str, Checkpoint] = {cp.id: cp for cp in checkpoints}

        # Build lookup: outline node id → CanonicalOutlineNode
        node_lookup: dict[str, CanonicalOutlineNode] = {}
        self._index_outline_nodes(outline.nodes, node_lookup)

        # Build the merged tree
        root_children: list[ChecklistNode] = []
        for mapping in path_collection.mappings:
            cp = cp_lookup.get(mapping.checkpoint_id)
            if not cp:
                logger.warning("Checkpoint %s not found, skipping", mapping.checkpoint_id)
                continue
            self._insert_path(root_children, mapping.path, node_lookup, cp)

        return root_children

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_outline_node(self, raw: dict) -> CanonicalOutlineNode:
        """Recursively parse a raw dict into ``CanonicalOutlineNode``."""
        children = [self._parse_outline_node(c) for c in raw.get("children", [])]
        return CanonicalOutlineNode(
            id=raw["id"],
            display_text=raw["display_text"],
            node_type=raw.get("node_type", "group"),
            children=children,
        )

    def _outline_node_to_dict(self, node: CanonicalOutlineNode) -> dict:
        """Convert ``CanonicalOutlineNode`` to a plain dict for JSON serialisation."""
        return {
            "id": node.id,
            "display_text": node.display_text,
            "node_type": node.node_type,
            "children": [self._outline_node_to_dict(c) for c in node.children],
        }

    def _index_outline_nodes(
        self,
        nodes: Sequence[CanonicalOutlineNode],
        lookup: dict[str, CanonicalOutlineNode],
    ) -> None:
        """Recursively index all outline nodes by their ``id``."""
        for node in nodes:
            lookup[node.id] = node
            self._index_outline_nodes(node.children, lookup)

    def _insert_path(
        self,
        siblings: list[ChecklistNode],
        path: list[str],
        node_lookup: dict[str, CanonicalOutlineNode],
        checkpoint: Checkpoint,
    ) -> None:
        """Insert a checkpoint into the tree at the given path.

        Reuses existing nodes when the path segment already exists
        among *siblings*.
        """
        if not path:
            return

        segment_id = path[0]
        outline_node = node_lookup.get(segment_id)
        display_text = outline_node.display_text if outline_node else segment_id
        node_type = outline_node.node_type if outline_node else "group"

        # Find or create the node for this segment
        existing = None
        for s in siblings:
            if s.id == segment_id:
                existing = s
                break

        if existing is None:
            existing = ChecklistNode(
                id=segment_id,
                display_text=display_text,
                node_type=node_type if len(path) > 1 else "case",
                children=[],
                checkpoint_id=checkpoint.id if len(path) == 1 else None,
            )
            siblings.append(existing)

        # Recurse into remaining path segments
        if len(path) > 1:
            self._insert_path(existing.children, path[1:], node_lookup, checkpoint)


# ---------------------------------------------------------------------------
# Post-processing: attach test case data to outline tree (F-002 / F-006)
# ---------------------------------------------------------------------------


def attach_expected_results_to_outline(
    optimized_tree: list[ChecklistNode],
    test_cases: list[TestCase],
) -> list[ChecklistNode]:
    """Attach full test-case data to ``case`` nodes in *optimized_tree*.

    For every ``case`` node whose ``checkpoint_id`` matches one or more
    *test_cases*, the following fields are populated on the
    :class:`ChecklistNode`:

    - ``steps``
    - ``preconditions``
    - ``expected_results``
    - ``priority``
    - ``category``
    - ``evidence_refs``
    - ``test_case_ref``

    If a single ``checkpoint_id`` corresponds to **multiple** TestCase
    objects, the first TestCase is merged into the original node and each
    additional TestCase spawns a new *sibling* ``case`` node (inserted
    immediately after the original).

    The function also preserves the legacy behaviour of creating
    ``expected_result`` leaf children under ``group`` nodes when
    ``expected_results`` text is present.

    On any unexpected error the function logs a warning and returns the
    *unmodified* tree so that downstream processing is never blocked.
    """
    try:
        if not optimized_tree or not test_cases:
            return optimized_tree

        # ------------------------------------------------------------------
        # 1. Build reverse index: checkpoint_id → list[TestCase]
        # ------------------------------------------------------------------
        cp_to_cases: Dict[str, List[TestCase]] = defaultdict(list)
        for tc in test_cases:
            if tc.checkpoint_id:
                cp_to_cases[tc.checkpoint_id].append(tc)

        # ------------------------------------------------------------------
        # 2. Recursive walk & enrichment
        # ------------------------------------------------------------------
        def _enrich_children(children: list[ChecklistNode]) -> list[ChecklistNode]:
            """Return a (possibly expanded) list of enriched children."""
            new_children: list[ChecklistNode] = []
            for node in children:
                # --- Recurse into group-like (non-leaf) nodes first ---
                if node.children:
                    node.children = _enrich_children(node.children)

                # --- Legacy: create expected_result leaf under group nodes ---
                if node.node_type not in ("case", "expected_result") and node.checkpoint_id:
                    matching = cp_to_cases.get(node.checkpoint_id, [])
                    for tc in matching:
                        if tc.expected_results:
                            er_node = ChecklistNode(
                                id=f"{node.id}__er__{tc.id}",
                                display_text=tc.expected_results,
                                node_type="expected_result",
                                children=[],
                                checkpoint_id=node.checkpoint_id,
                            )
                            node.children.append(er_node)

                # --- Core: enrich case nodes with full TestCase data ---
                if node.node_type == "case" and node.checkpoint_id:
                    matching = cp_to_cases.get(node.checkpoint_id, [])
                    if not matching:
                        new_children.append(node)
                        continue

                    # First TestCase → merge into the original node
                    first_tc = matching[0]
                    _fill_node_from_testcase(node, first_tc)
                    new_children.append(node)

                    # Additional TestCases → create sibling case nodes
                    for extra_tc in matching[1:]:
                        sibling = ChecklistNode(
                            id=f"{node.id}__tc__{extra_tc.id}",
                            display_text=extra_tc.title or node.display_text,
                            node_type="case",
                            children=[],
                            checkpoint_id=node.checkpoint_id,
                        )
                        _fill_node_from_testcase(sibling, extra_tc)
                        new_children.append(sibling)
                else:
                    new_children.append(node)

            return new_children

        optimized_tree = _enrich_children(optimized_tree)
        return optimized_tree

    except Exception:
        logger.warning(
            "attach_expected_results_to_outline failed; returning unmodified tree",
            exc_info=True,
        )
        return optimized_tree


def _fill_node_from_testcase(node: ChecklistNode, tc: TestCase) -> None:
    """Populate *node* fields from a single :class:`TestCase`."""
    node.steps = getattr(tc, "steps", None) or ""
    node.preconditions = getattr(tc, "preconditions", None) or ""
    node.expected_results = getattr(tc, "expected_results", None) or ""
    node.priority = getattr(tc, "priority", None) or ""
    node.category = getattr(tc, "category", None) or ""
    node.evidence_refs = getattr(tc, "evidence_refs", None) or []
    node.test_case_ref = getattr(tc, "id", None) or ""
