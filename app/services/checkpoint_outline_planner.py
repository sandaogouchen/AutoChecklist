"""Checkpoint 大纲规划服务。

在 testcase 草稿生成前规划固定层级：
1. 先产出可复用的规范大纲节点
2. 再将每个 checkpoint 映射到固定路径
3. 最后确定性构建共享 ``optimized_tree``

新增强制骨架约束：
- 当存在 mandatory_skeleton 时，将强制骨架注入 LLM prompt
- LLM 输出后执行确定性后处理修复，确保强制层级 100% 合规

新增 XMind 参考结构支持：
- 双模式 prompt 策略：仅参考模式（主结构锚点）与模版+参考模式（路由辅助）
- 参考结构可影响大纲维度覆盖、命名风格和 checkpoint 归属路由

新增 4 阶段规划流程：
- Stage 0: 准备参考树种子
- Stage 1: 覆盖度过滤，确定增量 checkpoint
- Stage 2: LLM 只对增量 checkpoint 做 Stage A/B
- Stage 3: 合并 reference_tree + llm_tree

新增分批规划支持（v2）：
- 当 active_checkpoints 超过 batch_threshold 时自动分批
- 按 PRD section（source_section）分组，保证同一段落的 checkpoint 一起处理
- 串行执行各 batch 的 Stage A/B，注入先前 batch 的 outline 摘要保证命名一致
- 确定性跨 batch 去重合并，无额外 LLM 调用
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.clients.llm import LLMClient
from app.config.settings import get_settings
from app.domain.case_models import TestCase
from app.domain.checklist_models import (
    CanonicalOutlineNode,
    CanonicalOutlineNodeCollection,
    ChecklistNode,
    CheckpointPathCollection,
    CheckpointPathMapping,
)
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import ResearchFact, ResearchOutput
from app.domain.state import CaseGenState
from app.domain.template_models import MandatorySkeletonNode
from app.domain.xmind_reference_models import XMindReferenceSummary
from app.services.coverage_detector import CoverageResult

logger = logging.getLogger(__name__)


_OUTLINE_SYSTEM_PROMPT = """你是资深测试架构师。
请基于提供的 checkpoints 设计一组“稳定、可复用、面向功能语义”的共享测试大纲节点。

输出原则：
1. 节点只表达业务对象/上下文/操作，不写预期结果。
2. 优先复用高层语义，不为每个 checkpoint 建孤立路径。
3. 每个 checkpoint 应落在 2~4 层的稳定路径下。
4. display_text 使用中文短语，语义稳定，避免“验证/检查/确认”等结果导向措辞。
5. semantic_key 使用英文 snake_case，体现稳定语义。
6. kind 仅允许：business_object / context / action。
7. visibility 仅允许：visible / hidden。
8. aliases 可为空；如有别名请提供常见同义表达。
9. 如提供了 mandatory_skeleton，所有输出节点与路径必须严格满足强制层级约束：
   - 强制可见层级必须出现在最终路径中；
   - hidden 节点只能作为过渡层，不能替代 mandatory visible 节点；
   - 不得合并、改写或省略强制骨架节点的 display_text 与层级关系。
10. 如果提供了参考结构（XMind），应优先参考其高层维度、命名风格和模块边界，但不要机械复制与 checkpoint 无关的节点。
"""

_PATH_SYSTEM_PROMPT = """你是资深测试架构师。
请将每个 checkpoint 映射到给定 canonical outline nodes 组成的一条稳定路径。

输出原则：
1. path_node_ids 必须引用 canonical outline nodes 中存在的 node_id。
2. 路径顺序应从高层语义到低层操作，长度通常 2~4。
3. 不得创建新节点，不得填入未知 node_id。
4. 每个 checkpoint 都必须返回一条路径。
5. 如提供了 mandatory_skeleton，路径必须严格满足强制层级约束：
   - 每条路径都必须包含 mandatory visible 节点；
   - hidden 节点仅可作为过渡，不得替代 mandatory visible 层；
   - 不得调整 mandatory 节点之间的层级顺序。
6. 如果提供了参考结构（XMind），应优先采用与参考结构一致的高层路由，但仍要以给定 canonical nodes 为准。
"""

_MANDATORY_CONSTRAINT_TEMPLATE = """\
## Mandatory Skeleton Constraints
You must strictly follow the mandatory skeleton below when generating nodes or paths.
- Keep every mandatory visible node as-is in display text and hierarchy.
- Hidden nodes may only be used as optional transitions and must not replace mandatory visible nodes.
- Do not merge, rename, delete, or reorder mandatory visible nodes.

Mandatory skeleton:
{skeleton_text}
"""

_REFERENCE_ONLY_GUIDANCE = """\
\n## XMind Reference Structure (authoritative naming/style anchor)
Use the following reference structure as a naming and routing anchor for high-level dimensions and module boundaries.
Do not copy irrelevant nodes mechanically; only keep nodes that help organize the provided checkpoints.
"""

_TEMPLATE_REFERENCE_GUIDANCE = """\
\n## XMind Template + Reference Structure
The following XMind structure contains both template routing hints and reference semantic anchors.
Prefer its top-level dimensions and stable naming when they fit the provided checkpoints.
Do not force unrelated template branches into the final tree.
"""


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().lower()


@dataclass
class _OutlineTrieNode:
    label: str
    children: dict[str, "_OutlineTrieNode"] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 分批规划辅助数据结构
# ---------------------------------------------------------------------------


@dataclass
class _BatchGroup:
    """一个分批组，包含同一 PRD section 的 checkpoint。"""
    section_name: str
    checkpoints: list[Checkpoint]


class CheckpointOutlinePlanner:
    """将 checkpoint 规划为稳定的共享大纲树。"""

    def __init__(
        self,
        llm_client: LLMClient,
        batch_threshold: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.llm_client = llm_client
        settings = get_settings()
        self.batch_threshold = (
            batch_threshold
            if batch_threshold is not None
            else settings.checkpoint_batch_threshold
        )
        self.batch_size = (
            batch_size
            if batch_size is not None
            else settings.checkpoint_batch_size
        )

    # ------------------------------------------------------------------
    # 分批规划：分组
    # ------------------------------------------------------------------

    def _group_checkpoints_by_section(
        self,
        checkpoints: list[Checkpoint],
        research_output: ResearchOutput,
    ) -> list[_BatchGroup]:
        """按 PRD source_section 将 checkpoint 分组。

        分组策略：
        1. 建立 fact_id → source_section 索引
        2. 每个 checkpoint 取其 fact_ids 对应的 source_section 的多数票
        3. 同一 section 的 checkpoint 归入一组
        4. 如果某组超过 batch_size，拆分为多个子组
        5. 如果 section 信息缺失，使用等分 fallback
        """
        fact_section_map: dict[str, str] = {}
        for fact in research_output.facts:
            section = getattr(fact, "source_section", "") or ""
            if section:
                fact_section_map[fact.fact_id] = section

        if not fact_section_map:
            logger.info("无 source_section 信息，使用等分 fallback 分组")
            return self._equal_split_groups(checkpoints)

        section_groups: dict[str, list[Checkpoint]] = defaultdict(list)
        unassigned: list[Checkpoint] = []

        for cp in checkpoints:
            section_votes: dict[str, int] = defaultdict(int)
            for fid in cp.fact_ids:
                sec = fact_section_map.get(fid, "")
                if sec:
                    section_votes[sec] += 1

            if section_votes:
                winning_section = max(section_votes, key=section_votes.get)
                section_groups[winning_section].append(cp)
            else:
                unassigned.append(cp)

        if unassigned:
            section_groups["__unassigned__"] = unassigned

        groups: list[_BatchGroup] = []
        for section_name, cps in section_groups.items():
            if len(cps) <= self.batch_size:
                groups.append(_BatchGroup(section_name=section_name, checkpoints=cps))
            else:
                for i in range(0, len(cps), self.batch_size):
                    chunk = cps[i : i + self.batch_size]
                    suffix = f" (part {i // self.batch_size + 1})"
                    groups.append(
                        _BatchGroup(
                            section_name=section_name + suffix,
                            checkpoints=chunk,
                        )
                    )

        logger.info(
            "Checkpoint 分组完成: %d 个 checkpoint → %d 个 batch (sections: %s)",
            len(checkpoints),
            len(groups),
            ", ".join(g.section_name for g in groups),
        )
        return groups

    def _equal_split_groups(
        self,
        checkpoints: list[Checkpoint],
    ) -> list[_BatchGroup]:
        """等分 fallback：当 source_section 缺失时按 batch_size 等分。"""
        groups: list[_BatchGroup] = []
        num_batches = math.ceil(len(checkpoints) / self.batch_size)
        for i in range(num_batches):
            chunk = checkpoints[i * self.batch_size : (i + 1) * self.batch_size]
            groups.append(
                _BatchGroup(
                    section_name=f"batch_{i + 1}",
                    checkpoints=chunk,
                )
            )
        return groups

    # ------------------------------------------------------------------
    # 分批规划：串行执行 Stage A/B
    # ------------------------------------------------------------------

    def _execute_batched_stage2(
        self,
        groups: list[_BatchGroup],
        facts_payload: list[dict],
        outline_system: str,
        path_system: str,
        xmind_section: str,
        mandatory_skeleton: MandatorySkeletonNode | None,
    ) -> tuple[list[CanonicalOutlineNode], list[CheckpointPathMapping]]:
        """串行执行各 batch 的 Stage A + Stage B。

        每个 batch 的 Stage A prompt 注入先前所有 batch 产出的
        outline 节点摘要，确保跨 batch 命名一致。
        执行完成后进行跨 batch 去重合并。
        """
        all_raw_nodes: list[CanonicalOutlineNode] = []
        all_raw_paths: list[CheckpointPathMapping] = []
        prior_node_summaries: list[str] = []

        for batch_idx, group in enumerate(groups):
            logger.info(
                "执行 batch %d/%d [%s]: %d checkpoints",
                batch_idx + 1,
                len(groups),
                group.section_name,
                len(group.checkpoints),
            )

            batch_checkpoint_payload = [
                {
                    "checkpoint_id": cp.checkpoint_id,
                    "title": cp.title,
                    "objective": cp.objective,
                    "category": cp.category,
                    "risk": cp.risk,
                    "preconditions": cp.preconditions,
                    "fact_ids": cp.fact_ids,
                }
                for cp in group.checkpoints
            ]

            batch_user_prompt = (
                "[Facts]\n"
                f"{json.dumps(facts_payload, ensure_ascii=False, indent=2)}\n\n"
                "[Checkpoints]\n"
                f"{json.dumps(batch_checkpoint_payload, ensure_ascii=False, indent=2)}"
            )

            if prior_node_summaries:
                prior_context = "\n".join(prior_node_summaries)
                batch_user_prompt += (
                    "\n\n## Prior Batch Outline Nodes (for naming consistency)\n"
                    "The following outline nodes were produced by earlier batches. "
                    "Reuse the same node IDs and display_text when the semantic "
                    "meaning overlaps. Do NOT duplicate them — only reference them "
                    "in your path mappings if applicable.\n\n"
                    f"{prior_context}"
                )

            if xmind_section:
                batch_user_prompt += xmind_section

            canonical_response = self.llm_client.generate_structured(
                system_prompt=outline_system,
                user_prompt=batch_user_prompt,
                response_model=CanonicalOutlineNodeCollection,
            )

            path_response = self.llm_client.generate_structured(
                system_prompt=path_system,
                user_prompt=self._build_path_prompt(
                    group.checkpoints,
                    canonical_response.canonical_nodes,
                ),
                response_model=CheckpointPathCollection,
            )

            all_raw_nodes.extend(canonical_response.canonical_nodes)
            all_raw_paths.extend(path_response.checkpoint_paths)

            summary_lines = []
            for node in canonical_response.canonical_nodes:
                summary_lines.append(
                    f"- {node.node_id}: {node.display_text} "
                    f"(kind={node.kind}, visibility={node.visibility})"
                )
            if summary_lines:
                prior_node_summaries.append(
                    f"### Batch {batch_idx + 1} — {group.section_name}\n"
                    + "\n".join(summary_lines)
                )

        deduped_nodes, id_remap = self._deduplicate_outline_nodes(all_raw_nodes)
        remapped_paths = self._remap_paths(all_raw_paths, id_remap)

        logger.info(
            "跨 batch 去重完成: %d raw nodes → %d deduped nodes, %d remaps",
            len(all_raw_nodes),
            len(deduped_nodes),
            len(id_remap),
        )

        return deduped_nodes, remapped_paths

    # ------------------------------------------------------------------
    # 跨 batch 去重
    # ------------------------------------------------------------------

    def _deduplicate_outline_nodes(
        self,
        nodes: list[CanonicalOutlineNode],
    ) -> tuple[list[CanonicalOutlineNode], dict[str, str]]:
        """基于 normalized_label 去重 outline 节点。

        返回 (去重后的节点列表, old_id → canonical_id 的重映射字典)。
        重映射字典只包含被替换掉的节点映射，保留节点不在其中。
        """
        id_remap: dict[str, str] = {}
        seen: dict[str, CanonicalOutlineNode] = {}

        for node in nodes:
            label = _normalize_text(node.display_text)
            if not label:
                seen[node.node_id] = node
                continue

            if label in seen:
                canonical = seen[label]
                if node.node_id != canonical.node_id:
                    id_remap[node.node_id] = canonical.node_id
                    existing_aliases = set(canonical.aliases or [])
                    new_aliases = set(node.aliases or [])
                    merged = existing_aliases | new_aliases | {node.display_text}
                    canonical.aliases = sorted(merged - {canonical.display_text})
            else:
                seen[label] = node

        deduped = list(seen.values())
        return deduped, id_remap

    def _remap_paths(
        self,
        paths: list[CheckpointPathMapping],
        id_remap: dict[str, str],
    ) -> list[CheckpointPathMapping]:
        """应用 id_remap 将路径中的旧 node_id 替换为 canonical node_id。"""
        if not id_remap:
            return paths

        remapped: list[CheckpointPathMapping] = []
        for path in paths:
            new_ids = [id_remap.get(nid, nid) for nid in path.path_node_ids]
            remapped.append(
                CheckpointPathMapping(
                    checkpoint_id=path.checkpoint_id,
                    path_node_ids=new_ids,
                )
            )
        return remapped

    # ------------------------------------------------------------------
    # plan() 主入口
    # ------------------------------------------------------------------

    def plan(
        self,
        research_output: ResearchOutput,
        checkpoints: list[Checkpoint],
        existing_cases: list[TestCase] | None = None,
        coverage_result: CoverageResult | None = None,
        mandatory_skeleton: MandatorySkeletonNode | None = None,
        xmind_reference: XMindReferenceSummary | None = None,
    ) -> CheckpointOutlinePlan:
        facts_payload = [
            {
                "fact_id": fact.fact_id,
                "description": fact.description,
                "category": getattr(fact, "category", ""),
            }
            for fact in research_output.facts
        ]

        checkpoint_payload = [
            {
                "checkpoint_id": cp.checkpoint_id,
                "title": cp.title,
                "objective": cp.objective,
                "category": cp.category,
                "risk": cp.risk,
                "preconditions": cp.preconditions,
                "fact_ids": cp.fact_ids,
            }
            for cp in checkpoints
        ]

        outline_user_prompt = (
            "[Facts]\n"
            f"{json.dumps(facts_payload, ensure_ascii=False, indent=2)}\n\n"
            "[Checkpoints]\n"
            f"{json.dumps(checkpoint_payload, ensure_ascii=False, indent=2)}"
        )

        outline_system = _OUTLINE_SYSTEM_PROMPT
        xmind_section = ""
        if xmind_reference and xmind_reference.reference_markdown:
            guidance = (
                _TEMPLATE_REFERENCE_GUIDANCE
                if getattr(xmind_reference, "contains_template_overlay", False)
                else _REFERENCE_ONLY_GUIDANCE
            )
            xmind_section = (
                guidance
                + "\n\n```markdown\n"
                + xmind_reference.reference_markdown.strip()
                + "\n```"
            )
            outline_user_prompt += xmind_section

        if mandatory_skeleton:
            constraint = self._build_mandatory_constraint_prompt(mandatory_skeleton)
            outline_system = outline_system + "\n\n" + constraint

        reference_tree = self._build_reference_tree(existing_cases or [])

        active_checkpoints = checkpoints
        if coverage_result and coverage_result.uncovered_checkpoint_ids:
            uncovered_ids = set(coverage_result.uncovered_checkpoint_ids)
            active_checkpoints = [
                cp for cp in checkpoints
                if cp.checkpoint_id in uncovered_ids
            ]
            logger.info(
                "覆盖度过滤: %d/%d checkpoint 需要增量生成",
                len(active_checkpoints), len(checkpoints),
            )

        if active_checkpoints:
            use_batch = len(active_checkpoints) > self.batch_threshold

            if use_batch:
                logger.info(
                    "启用分批规划: %d checkpoints > threshold %d",
                    len(active_checkpoints),
                    self.batch_threshold,
                )
                groups = self._group_checkpoints_by_section(
                    active_checkpoints, research_output,
                )

                path_system = _PATH_SYSTEM_PROMPT
                if mandatory_skeleton:
                    constraint = self._build_mandatory_constraint_prompt(
                        mandatory_skeleton,
                    )
                    path_system = path_system + "\n\n" + constraint

                canonical_nodes, checkpoint_paths = self._execute_batched_stage2(
                    groups=groups,
                    facts_payload=facts_payload,
                    outline_system=outline_system,
                    path_system=path_system,
                    xmind_section=xmind_section,
                    mandatory_skeleton=mandatory_skeleton,
                )

                resolved_paths = self._resolve_checkpoint_paths(
                    active_checkpoints,
                    checkpoint_paths,
                    canonical_nodes,
                )
            else:
                canonical_response = self.llm_client.generate_structured(
                    system_prompt=outline_system,
                    user_prompt=outline_user_prompt,
                    response_model=CanonicalOutlineNodeCollection,
                )

                path_system = _PATH_SYSTEM_PROMPT
                if mandatory_skeleton:
                    constraint = self._build_mandatory_constraint_prompt(
                        mandatory_skeleton,
                    )
                    path_system = path_system + "\n\n" + constraint

                path_response = self.llm_client.generate_structured(
                    system_prompt=path_system,
                    user_prompt=self._build_path_prompt(
                        active_checkpoints,
                        canonical_response.canonical_nodes,
                    ),
                    response_model=CheckpointPathCollection,
                )

                canonical_nodes = canonical_response.canonical_nodes
                checkpoint_paths = path_response.checkpoint_paths

                resolved_paths = self._resolve_checkpoint_paths(
                    active_checkpoints,
                    checkpoint_paths,
                    canonical_nodes,
                )

            llm_tree = self._build_outline_tree(resolved_paths)
        else:
            llm_tree = []
            canonical_nodes = []
            checkpoint_paths = []

        optimized_tree = self._merge_reference_and_llm_trees(
            reference_tree=reference_tree,
            llm_tree=llm_tree,
        )

        if mandatory_skeleton:
            optimized_tree = self._enforce_mandatory_skeleton(
                optimized_tree, mandatory_skeleton
            )

        return CheckpointOutlinePlan(
            canonical_outline_nodes=canonical_nodes,
            checkpoint_paths=checkpoint_paths,
            optimized_tree=optimized_tree,
        )

    def _build_mandatory_constraint_prompt(
        self, skeleton: MandatorySkeletonNode
    ) -> str:
        """将强制骨架序列化为约束 prompt 文本。"""
        skeleton_text = self._serialize_skeleton(skeleton, indent=0)
        return _MANDATORY_CONSTRAINT_TEMPLATE.format(skeleton_text=skeleton_text)

    def _serialize_skeleton(
        self, node: MandatorySkeletonNode, indent: int
    ) -> str:
        prefix = "  " * indent
        marker = "[visible]" if node.visibility == "visible" else "[hidden]"
        lines = [f"{prefix}- {node.display_text} {marker}"]
        for child in node.children:
            lines.append(self._serialize_skeleton(child, indent + 1))
        return "\n".join(lines)

    def _build_reference_tree(self, existing_cases: list[TestCase]) -> list[ChecklistNode]:
        trie = _OutlineTrieNode(label="__root__")
        for case in existing_cases:
            if not case.checklist_path:
                continue
            self._insert_path(trie, case.checklist_path)
        return self._trie_to_tree(trie)

    def _insert_path(self, trie: _OutlineTrieNode, path: list[str]) -> None:
        node = trie
        for label in path:
            normalized = _normalize_text(label)
            if normalized not in node.children:
                node.children[normalized] = _OutlineTrieNode(label=label)
            node = node.children[normalized]

    def _trie_to_tree(self, trie: _OutlineTrieNode) -> list[ChecklistNode]:
        result: list[ChecklistNode] = []
        for child in trie.children.values():
            result.append(
                ChecklistNode(
                    id=self._stable_node_id([child.label]),
                    label=child.label,
                    children=self._trie_to_tree(child),
                )
            )
        return result

    def _build_path_prompt(
        self,
        checkpoints: list[Checkpoint],
        canonical_nodes: list[CanonicalOutlineNode],
    ) -> str:
        payload = {
            "checkpoints": [
                {
                    "checkpoint_id": cp.checkpoint_id,
                    "title": cp.title,
                    "objective": cp.objective,
                    "category": cp.category,
                    "risk": cp.risk,
                    "preconditions": cp.preconditions,
                    "fact_ids": cp.fact_ids,
                }
                for cp in checkpoints
            ],
            "canonical_outline_nodes": [
                {
                    "node_id": node.node_id,
                    "semantic_key": node.semantic_key,
                    "display_text": node.display_text,
                    "kind": node.kind,
                    "visibility": node.visibility,
                    "aliases": node.aliases,
                }
                for node in canonical_nodes
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _resolve_checkpoint_paths(
        self,
        checkpoints: list[Checkpoint],
        checkpoint_paths: list[CheckpointPathMapping],
        canonical_nodes: list[CanonicalOutlineNode],
    ) -> list[list[str]]:
        node_map = {node.node_id: node.display_text for node in canonical_nodes}
        path_map = {item.checkpoint_id: item.path_node_ids for item in checkpoint_paths}
        resolved: list[list[str]] = []
        for cp in checkpoints:
            node_ids = path_map.get(cp.checkpoint_id, [])
            labels = [node_map[node_id] for node_id in node_ids if node_id in node_map]
            if labels:
                resolved.append(labels)
            else:
                fallback = self._fallback_path_for_checkpoint(cp)
                resolved.append(fallback)
        return resolved

    def _fallback_path_for_checkpoint(self, checkpoint: Checkpoint) -> list[str]:
        parts = [checkpoint.category or "功能", checkpoint.title or checkpoint.checkpoint_id]
        return [part for part in parts if part]

    def _build_outline_tree(self, resolved_paths: list[list[str]]) -> list[ChecklistNode]:
        trie = _OutlineTrieNode(label="__root__")
        for path in resolved_paths:
            self._insert_path(trie, path)
        return self._trie_to_tree(trie)

    def _merge_reference_and_llm_trees(
        self,
        reference_tree: list[ChecklistNode],
        llm_tree: list[ChecklistNode],
    ) -> list[ChecklistNode]:
        merged = {node.label: node for node in reference_tree}
        for node in llm_tree:
            if node.label not in merged:
                merged[node.label] = node
            else:
                merged[node.label].children = self._merge_reference_and_llm_trees(
                    merged[node.label].children,
                    node.children,
                )
        return list(merged.values())

    def _enforce_mandatory_skeleton(
        self,
        optimized_tree: list[ChecklistNode],
        mandatory_skeleton: MandatorySkeletonNode,
    ) -> list[ChecklistNode]:
        mandatory_tree = self._skeleton_to_tree(mandatory_skeleton)
        return self._merge_reference_and_llm_trees(mandatory_tree, optimized_tree)

    def _skeleton_to_tree(self, node: MandatorySkeletonNode) -> list[ChecklistNode]:
        return [
            ChecklistNode(
                id=self._stable_node_id([node.display_text]),
                label=node.display_text,
                children=[child for skeleton_child in node.children for child in self._skeleton_to_tree(skeleton_child)],
            )
        ]

    def _stable_node_id(self, path: list[str]) -> str:
        raw = "::".join(path)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


@dataclass
class CheckpointOutlinePlan:
    canonical_outline_nodes: list[CanonicalOutlineNode]
    checkpoint_paths: list[CheckpointPathMapping]
    optimized_tree: list[ChecklistNode]


def build_checkpoint_outline_planner_node(llm_client: LLMClient):
    planner = CheckpointOutlinePlanner(llm_client)

    def _node(state: CaseGenState) -> CaseGenState:
        plan = planner.plan(
            research_output=state.research_output,
            checkpoints=state.checkpoints,
            existing_cases=state.existing_cases,
            coverage_result=state.coverage_result,
            mandatory_skeleton=state.mandatory_skeleton,
            xmind_reference=state.xmind_reference,
        )
        state.checkpoint_outline_plan = plan
        return state

    return _node
