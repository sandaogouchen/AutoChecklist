"""Checkpoint 大纲规划服务。

在 testcase 草稿生成前规划固定层级：
1. 先产出可复用的规范大纲节点
2. 再将每个 checkpoint 映射到固定路径
3. 最后确定性构建共享 ``optimized_tree``

新增强制骨架约束：
- 当存在 mandatory_skeleton 时，将强制骨架注入 LLM prompt
- LLM 输出后执行确定性后处理修复，确保强制层级 100% 合规

改造后的 2 阶段规划流程（维度引导式全量规划）：
- Stage 1（维度引导大纲）: 若有 abstracted_reference_schema，构建维度引导
  prompt，告知 LLM 需要覆盖的验证维度方向（不含具体用例文本）
- Stage 2（全量 LLM 生成）: 对**所有** checkpoint 调用 LLM 生成完整大纲树，
  不再区分增量/已覆盖，不再用参考树做种子或合并

废弃的旧 4 阶段流程：
- Stage 0: 准备参考树种子 → 已废弃
- Stage 1: 覆盖度过滤 → 已改造为维度引导
- Stage 2: LLM 只对增量做 Stage A/B → 已改造为全量生成
- Stage 3: 合并 reference_tree + llm_tree → 已废弃
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass, field

from app.clients.llm import LLMClient
from app.domain.abstracted_reference_models import (
    AbstractedModule,
    AbstractedReferenceSchema,
    AbstractedSubmodule,
)
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
from app.domain.template_models import MandatorySkeletonNode
from app.domain.xmind_reference_models import XMindReferenceSummary
from app.services.coverage_detector import CoverageResult

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

_MANDATORY_CONSTRAINT_TEMPLATE = """
## 强制模版约束

以下是本次生成必须严格遵循的模版骨架结构。标记为 [MANDATORY] 的节点是强制节点，
你不可以增加、删除、修改或重命名这些节点。

强制骨架：
{skeleton_text}

约束规则：
1. 强制层级的节点必须与上述骨架完全一致
2. 所有 checkpoint 必须被分配到上述骨架节点的某个子路径下
3. 在非强制层级，你可以自由创建子节点来进一步组织 checkpoint
4. 输出的 JSON 中，强制节点必须保留原始 id 和 title，不可更改
""".strip()

_DIMENSION_GUIDANCE_TEMPLATE = """
## 参考模板维度指引（仅作为覆盖方向参考，禁止照搬）

以下验证维度清单来自同类项目的历史测试模板。
规划大纲时，确保覆盖与当前 PRD 相关的维度，忽略不相关的维度。
不要照搬维度的文字描述作为节点名称，而是基于当前 PRD 的具体内容生成节点。

{dimensions_text}
""".strip()


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


# ---------------------------------------------------------------------------
# 维度引导构建辅助函数
# ---------------------------------------------------------------------------


def _build_dimension_guidance_text(
    schema: AbstractedReferenceSchema,
) -> str:
    """将 AbstractedReferenceSchema 转为维度引导 prompt 文本。

    输出格式：
    ### 模块: FE（模版广告创编）[category: frontend_e2e]
    #### 子模块: 草稿创建
    - [positive] 草稿CRUD全生命周期: 验证草稿从创建到删除的完整操作流程
    - [negative] 异常输入容错: 验证非法或边界输入下系统的容错处理
    ...
    """
    if not schema or not schema.modules:
        return ""

    lines: list[str] = []
    for module in schema.modules:
        lines.append(
            f"### 模块: {module.title} [category: {module.category}]"
        )
        if module.boundary_hints:
            hints_str = ", ".join(module.boundary_hints[:10])
            lines.append(f"  边界提示: {hints_str}")

        for submodule in module.submodules:
            density_tag = ""
            if submodule.density and submodule.density != "normal":
                density_tag = f" (density: {submodule.density})"
            lines.append(f"#### 子模块: {submodule.title}{density_tag}")

            for dim in submodule.dimensions:
                lines.append(
                    f"- [{dim.mode}] {dim.name}: {dim.description}"
                )

        lines.append("")  # blank line between modules

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# XMind 参考结构辅助函数（向后兼容，降级使用）
# ---------------------------------------------------------------------------


def _get_formatted_summary(xmind_reference_summary) -> str:
    """Safely extract formatted_summary from Pydantic model or dict."""
    if xmind_reference_summary is None:
        return ""
    if hasattr(xmind_reference_summary, "formatted_summary"):
        return xmind_reference_summary.formatted_summary or ""
    if isinstance(xmind_reference_summary, dict):
        return xmind_reference_summary.get("formatted_summary", "")
    return ""


def _build_xmind_fallback_prompt_section(
    xmind_reference_summary,
    has_mandatory_skeleton: bool,
) -> str:
    """构建 XMind 参考摘要的降级 prompt 段落。

    仅在没有 abstracted_reference_schema 时使用，作为向后兼容的降级路径。
    与旧版不同的是：不再引导 LLM 照搬参考结构，而是仅提供结构概览作为参考。
    """
    formatted = _get_formatted_summary(xmind_reference_summary)
    if not formatted:
        return ""

    return (
        "\n\n## 参考 Checklist 结构概览（仅供参考，禁止照搬）\n"
        f"{formatted}\n"
        "【重要指令】上述参考结构仅用于了解历史模板的覆盖范围。\n"
        "你必须基于当前 PRD 需求全新生成所有节点，禁止复制参考结构中的任何具体文本。\n"
        "仅参考其覆盖的测试维度方向。\n"
    )


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


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
    """将 checkpoint 规划为稳定的共享大纲树。

    改造后采用维度引导式全量规划：
    - 不再将参考树作为种子或合并目标
    - 通过 AbstractedReferenceSchema 提供覆盖维度引导
    - 所有 checkpoint 均由 LLM 全量规划，输出即为完整大纲
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def plan(
        self,
        research_output: ResearchOutput,
        checkpoints: list[Checkpoint],
        mandatory_skeleton: MandatorySkeletonNode | None = None,
        xmind_reference_summary=None,
        coverage_result: CoverageResult | None = None,
        abstracted_reference_schema: AbstractedReferenceSchema | None = None,
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

        # ---- 构建 system prompt（含可选的强制约束）----
        outline_system = _OUTLINE_SYSTEM_PROMPT
        if mandatory_skeleton:
            constraint = self._build_mandatory_constraint_prompt(mandatory_skeleton)
            outline_system = outline_system + "\n\n" + constraint

        # ---- Stage 1: 维度引导构建 ----
        dimension_guidance = ""
        if abstracted_reference_schema and abstracted_reference_schema.modules:
            dimension_guidance = _build_dimension_guidance_text(
                abstracted_reference_schema
            )
            logger.info(
                "维度引导已构建: modules=%d, total_dimensions=%d",
                len(abstracted_reference_schema.modules),
                abstracted_reference_schema.total_dimensions,
            )

        # 注入维度引导到 system prompt
        if dimension_guidance:
            guidance_section = _DIMENSION_GUIDANCE_TEMPLATE.format(
                dimensions_text=dimension_guidance
            )
            outline_system = outline_system + "\n\n" + guidance_section
        elif xmind_reference_summary:
            # 降级路径：没有抽象 schema 时，使用 XMind 摘要作为弱参考
            # 但不再像旧版那样鼓励照搬
            fallback_section = _build_xmind_fallback_prompt_section(
                xmind_reference_summary=xmind_reference_summary,
                has_mandatory_skeleton=mandatory_skeleton is not None,
            )
            if fallback_section:
                outline_system = outline_system + fallback_section

        # ---- Stage 2: 全量 LLM 生成（所有 checkpoint，不区分增量/已覆盖）----
        outline_user_prompt = (
            "[Facts]\n"
            f"{json.dumps(facts_payload, ensure_ascii=False, indent=2)}\n\n"
            "[Checkpoints]\n"
            f"{json.dumps(checkpoint_payload, ensure_ascii=False, indent=2)}"
        )

        if dimension_guidance:
            outline_user_prompt += (
                "\n\n[Generation Directive]\n"
                "Based on the PRD requirements and the verification dimensions above "
                "(as abstract guidance), generate a COMPLETE checklist tree. "
                "DO NOT copy any specific test case text — create new, PRD-specific "
                "test cases that cover these verification dimensions.\n"
                "ALL checkpoints listed above must be organized into the outline. "
                "No checkpoint should be skipped or considered 'already covered'."
            )

        canonical_response = self.llm_client.generate_structured(
            system_prompt=outline_system,
            user_prompt=outline_user_prompt,
            response_model=CanonicalOutlineNodeCollection,
        )

        path_system = _PATH_SYSTEM_PROMPT
        if mandatory_skeleton:
            constraint = self._build_mandatory_constraint_prompt(mandatory_skeleton)
            path_system = path_system + "\n\n" + constraint

        path_response = self.llm_client.generate_structured(
            system_prompt=path_system,
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

        # LLM 输出即为完整大纲——不再与参考树合并
        optimized_tree = self._build_outline_tree(resolved_paths)

        # 如果存在强制骨架，执行后处理修复
        if mandatory_skeleton:
            optimized_tree = self._enforce_mandatory_skeleton(
                optimized_tree, mandatory_skeleton
            )

        return CheckpointOutlinePlan(
            canonical_outline_nodes=canonical_response.canonical_nodes,
            checkpoint_paths=path_response.checkpoint_paths,
            optimized_tree=optimized_tree,
        )

    # ------------------------------------------------------------------
    # 强制骨架相关方法
    # ------------------------------------------------------------------

    def _build_mandatory_constraint_prompt(
        self, skeleton: MandatorySkeletonNode
    ) -> str:
        """将强制骨架序列化为约束 prompt 文本。"""
        skeleton_text = self._serialize_skeleton(skeleton, indent=0)
        return _MANDATORY_CONSTRAINT_TEMPLATE.format(skeleton_text=skeleton_text)

    def _serialize_skeleton(
        self, node: MandatorySkeletonNode, indent: int
    ) -> str:
        """将骨架节点树序列化为缩进文本。"""
        lines: list[str] = []
        if node.id != "__mandatory_root__":
            prefix = "  " * indent
            mandatory_tag = " [MANDATORY]" if node.is_mandatory else ""
            lines.append(f"{prefix}- {node.id}: {node.title}{mandatory_tag}")
        for child in node.children:
            lines.extend(
                self._serialize_skeleton(child, indent + (0 if node.id == "__mandatory_root__" else 1)).splitlines()
            )
        return "\n".join(lines)

    def _enforce_mandatory_skeleton(
        self,
        optimized_tree: list[ChecklistNode],
        skeleton: MandatorySkeletonNode,
    ) -> list[ChecklistNode]:
        """后处理修复：确保 optimized_tree 的强制层级与骨架一致。

        策略：以强制骨架为 ground truth，将骨架中的强制节点
        与 LLM 生成的树进行合并。骨架节点保留 LLM 为其生成的子节点。
        """
        if not skeleton or not skeleton.children:
            return optimized_tree

        # 建立 LLM 生成树的 node_id 索引
        llm_lookup: dict[str, ChecklistNode] = {}
        for node in optimized_tree:
            self._index_nodes(node, llm_lookup)

        result: list[ChecklistNode] = []
        for skeleton_child in skeleton.children:
            merged = self._merge_skeleton_node(skeleton_child, llm_lookup)
            result.append(merged)

        # 收集未被骨架覆盖的 LLM 节点（非强制层级的额外节点）
        skeleton_ids = self._collect_skeleton_ids(skeleton)
        for node in optimized_tree:
            if node.node_id not in skeleton_ids and node.node_id not in {
                n.node_id for n in result
            }:
                result.append(node)

        logger.info(
            "强制约束后处理完成: 骨架节点=%d, 最终树根节点=%d",
            len(skeleton.children),
            len(result),
        )
        return result

    def _merge_skeleton_node(
        self,
        skeleton_node: MandatorySkeletonNode,
        llm_lookup: dict[str, ChecklistNode],
    ) -> ChecklistNode:
        """将骨架节点与 LLM 生成的对应节点合并。"""
        llm_node = llm_lookup.get(skeleton_node.id)

        # 递归处理子节点
        merged_children: list[ChecklistNode] = []
        skeleton_child_ids = {c.id for c in skeleton_node.children}

        for skeleton_child in skeleton_node.children:
            merged_children.append(
                self._merge_skeleton_node(skeleton_child, llm_lookup)
            )

        # 保留 LLM 为该节点生成的非骨架子节点
        if llm_node:
            for llm_child in llm_node.children:
                if llm_child.node_id not in skeleton_child_ids:
                    merged_children.append(llm_child)

        priority = skeleton_node.original_metadata.get("priority", "P2")

        return ChecklistNode(
            node_id=skeleton_node.id,
            title=skeleton_node.title,
            node_type="group",
            hidden=False,
            source="template",
            is_mandatory=skeleton_node.is_mandatory,
            priority=priority,
            children=merged_children,
        )

    def _index_nodes(
        self, node: ChecklistNode, lookup: dict[str, ChecklistNode]
    ) -> None:
        """递归索引节点。"""
        if node.node_id:
            lookup[node.node_id] = node
        for child in node.children:
            self._index_nodes(child, lookup)

    def _collect_skeleton_ids(self, node: MandatorySkeletonNode) -> set[str]:
        """收集骨架中所有节点 ID。"""
        ids = {node.id}
        for child in node.children:
            ids.update(self._collect_skeleton_ids(child))
        return ids

    # ------------------------------------------------------------------
    # 参考树合并 — 已废弃（DEPRECATED）
    # ------------------------------------------------------------------

    def _merge_reference_and_llm_trees(
        self,
        reference_tree: list[ChecklistNode],
        llm_tree: list[ChecklistNode],
    ) -> list[ChecklistNode]:
        """将 LLM 生成的增量节点合并进参考树。

        .. deprecated::
            此方法已废弃。改造后的规划流程不再使用参考树合并。
            LLM 全量生成的大纲即为完整输出，无需与参考树合并。
            保留此方法仅为向后兼容，不应在新代码中调用。

        合并策略（旧版）：
        1. 以 reference_tree 为主干
        2. 对 llm_tree 的每个一级节点，找标题相似的参考分支（Jaccard >= 0.4）
        3. 找到 → 将 LLM children 追加到参考分支下（去重后）
        4. 未找到 → 作为新一级分支追加
        5. 叶子去重：同一父节点下 Jaccard >= 0.5 则保留参考叶子
        """
        warnings.warn(
            "_merge_reference_and_llm_trees is deprecated. "
            "The new dimension-guided pipeline generates complete outlines "
            "without reference tree merging.",
            DeprecationWarning,
            stacklevel=2,
        )
        if not reference_tree:
            return llm_tree
        if not llm_tree:
            return reference_tree

        merged = [node.model_copy(deep=True) for node in reference_tree]
        ref_branch_index = {node.title: node for node in merged}

        for llm_node in llm_tree:
            best_match_title, best_score = self._find_best_branch_match(
                llm_node.title, list(ref_branch_index.keys()),
            )
            if best_score >= 0.4 and best_match_title:
                target = ref_branch_index[best_match_title]
                self._merge_children_dedup(target, llm_node.children)
            else:
                merged.append(llm_node)

        return merged

    def _merge_children_dedup(
        self,
        target: ChecklistNode,
        new_children: list[ChecklistNode],
    ) -> None:
        """将 new_children 追加到 target.children，叶子级去重。

        .. deprecated:: 仅供已废弃的 _merge_reference_and_llm_trees 使用。
        """
        existing_titles = {child.title for child in target.children}
        for child in new_children:
            is_duplicate = any(
                self._jaccard_char(child.title, existing) >= 0.5
                for existing in existing_titles
            )
            if not is_duplicate:
                target.children.append(child)
                existing_titles.add(child.title)

    @staticmethod
    def _find_best_branch_match(
        title: str,
        candidates: list[str],
    ) -> tuple[str | None, float]:
        """字符级 Jaccard 找最佳匹配分支。"""
        best_title: str | None = None
        best_score = 0.0
        title_chars = set(title)

        for candidate in candidates:
            cand_chars = set(candidate)
            union = title_chars | cand_chars
            if not union:
                continue
            score = len(title_chars & cand_chars) / len(union)
            if score > best_score:
                best_score = score
                best_title = candidate

        return best_title, best_score

    @staticmethod
    def _jaccard_char(a: str, b: str) -> float:
        """字符级 Jaccard 相似度。"""
        set_a, set_b = set(a), set(b)
        if not set_a and not set_b:
            return 1.0
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    # ------------------------------------------------------------------
    # 路径构建与树构建方法（保留不变）
    # ------------------------------------------------------------------

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
        mandatory_skeleton = state.get("mandatory_skeleton")
        xmind_reference_summary = state.get("xmind_reference_summary")
        coverage_result = state.get("coverage_result")
        abstracted_reference_schema = state.get("abstracted_reference_schema")
        checkpoints = state.get("checkpoints", [])

        plan = planner.plan(
            state.get("research_output", ResearchOutput()),
            checkpoints,
            mandatory_skeleton=mandatory_skeleton,
            xmind_reference_summary=xmind_reference_summary,
            coverage_result=coverage_result,
            abstracted_reference_schema=abstracted_reference_schema,
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
    """将 testcase 信息挂载到既有大纲树。"""
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
