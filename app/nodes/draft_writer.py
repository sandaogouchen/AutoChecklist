"""草稿编写节点。

调用 LLM 根据 checkpoint 列表和关联证据，生成初始版本的测试用例草稿。
每个生成的测试用例会携带对应的 checkpoint_id，建立可追溯的链路。

变更：在 _SYSTEM_PROMPT 中新增前置条件编写规范（5 条规则），
引导 LLM 生成高质量、可分组的 preconditions。

变更：参考叶子节点补充改为 ThreadPoolExecutor 并发，
batch_size 从 10 提升至 40，大幅缩短 draft_writer 耗时。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor

from pydantic import BaseModel, Field

from app.clients.llm import LLMClient
from app.domain.case_models import TestCase
from app.domain.checklist_models import (
    CanonicalOutlineNode,
    ChecklistNode,
    CheckpointPathMapping,
)
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可调常量
# ---------------------------------------------------------------------------
_REF_LEAF_BATCH_SIZE: int = 40
"""参考叶子节点每批处理数量。增大可减少 LLM 调用次数，但单次 prompt 更长。"""

_MAX_WORKERS: int = 5
"""ThreadPoolExecutor 并发线程数。控制同时发出的 LLM 请求数量。"""

# LLM 系统提示词：指导模型基于 checkpoint 生成结构化的手动 QA 测试用例
_SYSTEM_PROMPT = (
    "You write concise manual QA test cases as structured JSON. "
    "Each test case MUST include an id, title, steps, expected_results, evidence_refs, "
    "and a checkpoint_id field that references the checkpoint it was generated from. "
    "Always include ids, steps, expected_results, and evidence_refs.\n"
    "Fixed hierarchy paths are supplied by the system.\n"
    "Do not restate or merge that hierarchy into testcase titles, preconditions, "
    "or summary headings.\n"
    "Do not restate merged parent phrases such as `处于 CBO 的 Ad group 配置场景`.\n"
    "Generate only the leaf testcase title, concrete steps, and expected_results "
    "under the supplied path.\n\n"
    "【语言要求】\n"
    "- title 字段使用中文书写，简要概括测试目标。\n"
    "- steps 字段使用中文书写操作步骤，其中 UI 元素、按钮文案、字段名等"
    "专有名词保留英文原文并用反引号包裹，例如：点击 `Submit` 按钮。\n"
    "- expected_results 字段使用中文书写预期结果。\n"
    "- preconditions 字段使用中文书写前置条件。\n"
    "- id、priority、category、checkpoint_id 等标识字段保留英文。\n"
    "- evidence_refs 中的 section_title 和 excerpt 保留原文不翻译。\n\n"
    "【前置条件编写规范】\n"
    "preconditions 字段是后续自动分组的关键依据，请严格遵守以下规则：\n"
    "1. 表述规范化：使用统一的句式结构，同一含义只用一种表达方式。"
    "例如：始终使用「用户已登录系统」而非混用「登录状态下」「已完成登录」。\n"
    "2. 层级化描述：前置条件按逻辑顺序排列，从环境/系统状态 → 用户状态 → 数据准备 → 页面/入口。"
    "例如：[\"系统已部署 v2.0 版本\", \"用户已登录管理后台\", \"已创建至少一条测试数据\"]。\n"
    "3. 原子性：每条前置条件仅描述一个独立的准备动作或状态，不要合并多个条件到一句话中。"
    "错误示例：「用户已登录且进入设置页面」→ 应拆分为两条。\n"
    "4. 充分性：列出执行测试步骤前所需的全部准备条件，不遗漏隐含的前置状态。\n"
    "5. 复用意识：当多个测试用例共享相同的前置环境时，确保它们的 preconditions 完全一致"
    "（字面相同），以便自动归组。不要因措辞差异导致相同含义的条件被拆分到不同组。"
)


class DraftCaseCollection(BaseModel):
    """LLM 返回的测试用例草稿集合。"""

    test_cases: list[TestCase] = Field(default_factory=list)


def _collect_reference_leaves(tree: list[ChecklistNode]) -> list[ChecklistNode]:
    """递归收集参考树中所有叶子节点（source='reference'）。"""
    leaves: list[ChecklistNode] = []
    for node in tree:
        if not node.children and node.source == "reference":
            leaves.append(node)
        else:
            leaves.extend(_collect_reference_leaves(node.children))
    return leaves


# ---------------------------------------------------------------------------
# 并发参考叶子补充
# ---------------------------------------------------------------------------


def _build_ref_leaf_prompt(batch: list[ChecklistNode]) -> str:
    """为一批参考叶子节点构建 prompt。"""
    leaf_descriptions = "\n".join(
        f"- 【{leaf.title}】(node_id={leaf.node_id})"
        for leaf in batch
    )
    return (
        "以下是已有 Checklist 中的测试用例标题，请为每个标题补充具体的：\n"
        "1. 前置条件（preconditions）\n"
        "2. 执行步骤（steps）\n"
        "3. 预期结果（expected_results）\n\n"
        "【重要】请保留原始标题不做任何修改。\n\n"
        f"用例列表：\n{leaf_descriptions}\n"
    )


def _process_single_batch(
    llm_client: LLMClient,
    batch: list[ChecklistNode],
    batch_index: int,
    total_batches: int,
) -> tuple[list[TestCase], dict]:
    """处理单个批次的参考叶子节点。线程安全。

    Returns:
        (test_cases, timing_record)
    """
    start = time.monotonic()
    had_error = False
    cases: list[TestCase] = []

    try:
        prompt = _build_ref_leaf_prompt(batch)
        response = llm_client.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_model=DraftCaseCollection,
        )
        if response and hasattr(response, "test_cases"):
            for case, leaf in zip(response.test_cases, batch):
                if hasattr(case, "title"):
                    case.title = leaf.title
                if hasattr(case, "source"):
                    case.source = "reference"
            cases = list(response.test_cases)
    except Exception:
        had_error = True
        logger.warning(
            "参考叶子 batch %d/%d 生成失败，跳过",
            batch_index + 1,
            total_batches,
            exc_info=True,
        )

    elapsed = time.monotonic() - start
    logger.info(
        "[DRAFT-PARALLEL] batch %d/%d done, %d cases (%.1fs)%s",
        batch_index + 1,
        total_batches,
        len(cases),
        elapsed,
        "  \u2717 ERROR" if had_error else "",
    )

    timing_record = {
        "batch_index": batch_index,
        "leaf_count": len(batch),
        "case_count": len(cases),
        "elapsed_seconds": round(elapsed, 2),
        "had_error": had_error,
    }
    return cases, timing_record


def _generate_reference_leaf_details(
    llm_client: LLMClient,
    ref_leaves: list[ChecklistNode],
    state: dict,
) -> tuple[list[TestCase], dict]:
    """为参考树叶子节点并发批量生成 steps / expected_results / preconditions。

    标题固定为参考叶子的原始标题（不允许 LLM 修改）。
    使用 ThreadPoolExecutor 并发执行，批间无数据依赖。

    Returns:
        (all_cases, timing_metadata)
    """
    if not ref_leaves:
        return [], {
            "batch_size": _REF_LEAF_BATCH_SIZE,
            "max_workers": _MAX_WORKERS,
            "total_leaves": 0,
            "total_batches": 0,
            "total_elapsed_seconds": 0,
            "batches": [],
        }

    # 分批
    batches: list[list[ChecklistNode]] = [
        ref_leaves[i : i + _REF_LEAF_BATCH_SIZE]
        for i in range(0, len(ref_leaves), _REF_LEAF_BATCH_SIZE)
    ]
    total_batches = len(batches)

    logger.info(
        "[DRAFT-PARALLEL] 启动并发补充: %d 叶子, %d 批, batch_size=%d, workers=%d",
        len(ref_leaves),
        total_batches,
        _REF_LEAF_BATCH_SIZE,
        _MAX_WORKERS,
    )

    overall_start = time.monotonic()
    all_cases: list[TestCase] = []
    batch_timings: list[dict] = []

    # 并发执行——按 batch_index 排序保持稳定输出顺序
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures: dict[Future, int] = {}
        for idx, batch in enumerate(batches):
            future = pool.submit(
                _process_single_batch,
                llm_client,
                batch,
                idx,
                total_batches,
            )
            futures[future] = idx

        # 收集结果，按 batch_index 排序
        results_by_index: dict[int, tuple[list[TestCase], dict]] = {}
        for future in futures:
            idx = futures[future]
            try:
                results_by_index[idx] = future.result()
            except Exception:
                # 双重保险：_process_single_batch 内部已 catch，此处兜底
                logger.warning(
                    "参考叶子 batch %d future 异常，跳过", idx, exc_info=True,
                )
                results_by_index[idx] = (
                    [],
                    {
                        "batch_index": idx,
                        "leaf_count": len(batches[idx]),
                        "case_count": 0,
                        "elapsed_seconds": 0,
                        "had_error": True,
                    },
                )

    # 按 index 有序合并
    for idx in sorted(results_by_index.keys()):
        cases, timing = results_by_index[idx]
        all_cases.extend(cases)
        batch_timings.append(timing)

    overall_elapsed = time.monotonic() - overall_start

    logger.info(
        "[DRAFT-PARALLEL] 全部 %d 批完成，生成 %d 条用例，并发=%d (%.1fs)",
        total_batches,
        len(all_cases),
        _MAX_WORKERS,
        overall_elapsed,
    )

    timing_metadata = {
        "batch_size": _REF_LEAF_BATCH_SIZE,
        "max_workers": _MAX_WORKERS,
        "total_leaves": len(ref_leaves),
        "total_batches": total_batches,
        "total_elapsed_seconds": round(overall_elapsed, 2),
        "batches": batch_timings,
    }

    return all_cases, timing_metadata


class DraftWriterNode:
    """兼容 LangGraph 类节点接口的草稿编写节点。"""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def __call__(self, state: CaseGenState) -> CaseGenState:
        return _run_draft_writer(state, self._llm_client)


def build_draft_writer_node(llm_client: LLMClient):
    """构建草稿编写节点的工厂函数。"""

    return DraftWriterNode(llm_client)


def _run_draft_writer(state: CaseGenState, llm_client: LLMClient) -> CaseGenState:
    checkpoints = state.get("checkpoints", [])
    checkpoint_paths = state.get("checkpoint_paths", [])
    canonical_outline_nodes = state.get("canonical_outline_nodes", [])

    if checkpoints:
        prompt_lines = [
            _format_checkpoint_prompt(
                index,
                cp,
                checkpoint_paths,
                canonical_outline_nodes,
            )
            for index, cp in enumerate(checkpoints, start=1)
        ]
    else:
        scenarios = state.get("planned_scenarios", [])
        evidence = state.get("mapped_evidence", {})
        prompt_lines = [
            _format_scenario_prompt(index, scenario, evidence.get(scenario.title, []))
            for index, scenario in enumerate(scenarios, start=1)
        ]

    project_context_summary = state.get("project_context_summary", "")
    if project_context_summary:
        prompt_lines.insert(
            0,
            f"[Project Checklist Constraints]\n{project_context_summary}\n",
        )

    if not prompt_lines:
        return {"draft_cases": []}

    response = llm_client.generate_structured(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt="\n\n".join(prompt_lines),
        response_model=DraftCaseCollection,
    )
    draft_cases = response.test_cases

    # ---- 参考叶子节点并发补充 detail ----
    draft_writer_timing = None
    xmind_summary = state.get("xmind_reference_summary")
    if xmind_summary and hasattr(xmind_summary, "reference_tree"):
        ref_tree = xmind_summary.reference_tree
        if isinstance(ref_tree, list) and ref_tree:
            ref_leaves = _collect_reference_leaves(ref_tree)
            if ref_leaves:
                logger.info(
                    "为 %d 个参考叶子节点补充 case detail",
                    len(ref_leaves),
                )
                ref_cases, draft_writer_timing = _generate_reference_leaf_details(
                    llm_client, ref_leaves, state,
                )
                draft_cases.extend(ref_cases)

    result: dict = {"draft_cases": draft_cases}
    if draft_writer_timing is not None:
        result["draft_writer_timing"] = draft_writer_timing
    return result


def _format_checkpoint_prompt(
    index: int,
    checkpoint: Checkpoint,
    checkpoint_paths: list[CheckpointPathMapping],
    canonical_outline_nodes: list[CanonicalOutlineNode],
) -> str:
    """格式化单个 checkpoint 的 prompt 片段。"""
    lines = [
        f"Checkpoint {index}: {checkpoint.title}",
        f"Checkpoint ID: {checkpoint.checkpoint_id}",
        f"Objective: {checkpoint.objective}",
        f"Category: {checkpoint.category}",
        f"Risk: {checkpoint.risk}",
    ]

    if checkpoint.branch_hint:
        lines.append(f"Branch hint: {checkpoint.branch_hint}")

    if checkpoint.preconditions:
        lines.append("Preconditions:")
        lines.extend(f"- {pc}" for pc in checkpoint.preconditions)

    path_context = _resolve_path_context(
        checkpoint.checkpoint_id,
        checkpoint_paths,
        canonical_outline_nodes,
    )
    if path_context:
        lines.append("Fixed hierarchy path:")
        lines.extend(f"- {item}" for item in path_context)
        lines.append(
            "The hierarchy above already exists in optimized_tree. "
            "Generate only the leaf testcase content below this path."
        )

    lines.append(f"Source facts: {', '.join(checkpoint.fact_ids)}")

    if checkpoint.evidence_refs:
        lines.append("Evidence:")
        lines.extend(
            f"- {ref.section_title} ({ref.line_start}-{ref.line_end}): {ref.excerpt}"
            for ref in checkpoint.evidence_refs
        )

    lines.append(
        f"\nGenerate test case(s) for this checkpoint. Set checkpoint_id to '{checkpoint.checkpoint_id}'."
    )

    return "\n".join(lines)


def _resolve_path_context(
    checkpoint_id: str,
    checkpoint_paths: list[CheckpointPathMapping],
    canonical_outline_nodes: list[CanonicalOutlineNode],
) -> list[str]:
    path_mapping = next(
        (item for item in checkpoint_paths if item.checkpoint_id == checkpoint_id),
        None,
    )
    if path_mapping is None:
        return []

    node_lookup = {node.node_id: node for node in canonical_outline_nodes}
    resolved: list[str] = []
    for node_id in path_mapping.path_node_ids:
        node = node_lookup.get(node_id)
        if node is None or node.visibility == "hidden":
            continue
        resolved.append(node.display_text)

    return resolved


def _format_scenario_prompt(index: int, scenario, evidence_refs: list) -> str:
    """格式化单个场景的 prompt 片段（向后兼容）。"""
    lines = [
        f"Scenario {index}: {scenario.title}",
        f"Category: {scenario.category}",
        f"Risk: {scenario.risk}",
        f"Rationale: {scenario.rationale}",
        "Evidence:",
    ]
    lines.extend(
        f"- {ref.section_title} ({ref.line_start}-{ref.line_end}): {ref.excerpt}"
        for ref in evidence_refs
    )
    return "\n".join(lines)
