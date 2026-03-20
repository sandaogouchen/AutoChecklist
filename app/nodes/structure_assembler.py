"""结构组装节点。

对 LLM 生成的草稿用例进行标准化处理：
- 补全缺失的 ID（自动编号 TC-001, TC-002, ...）
- 为空字段填充默认值
- 补充缺失的证据引用（从 mapped_evidence 中查找）
- 保留并补全 checkpoint_id
- 对文本字段进行中英文混排规范化
- 从 checkpoint 继承模版绑定字段（兜底补全）
"""

from __future__ import annotations

import logging

from app.domain.case_models import TestCase
from app.domain.checkpoint_models import Checkpoint
from app.domain.state import CaseGenState
from app.services.checkpoint_outline_planner import attach_expected_results_to_outline
from app.services.text_normalizer import normalize_test_case

logger = logging.getLogger(__name__)


def structure_assembler_node(state: CaseGenState) -> CaseGenState:
    """组装并标准化测试用例。

    遍历所有草稿用例，对每个用例执行字段补全：
    - ID 为空时按序号自动生成（TC-001 格式）
    - 列表类字段为空时确保为空列表（而非 None）
    - 证据引用为空时尝试从 mapped_evidence 中按标题匹配
    - 保留 LLM 生成的 checkpoint_id
    - 对文本字段执行中英文混排规范化（normalize_test_case）
    - 兜底：从 checkpoint 继承模版绑定字段（当 draft_writer 未完成继承时）

    Returns:
        包含 ``test_cases``（已标准化的用例列表）的状态增量。
    """
    assembled_cases: list[TestCase] = []
    evidence_lookup = state.get("mapped_evidence", {})

    # 构建 checkpoint_id → Checkpoint 的查找表，用于模版字段兜底继承
    checkpoints: list[Checkpoint] = state.get("checkpoints", [])
    cp_lookup: dict[str, Checkpoint] = {
        cp.checkpoint_id: cp for cp in checkpoints if cp.checkpoint_id
    }

    for index, case in enumerate(state.get("draft_cases", []), start=1):
        update_fields = {
            "id": case.id or f"TC-{index:03d}",
            "preconditions": case.preconditions or [],
            "steps": case.steps or [],
            "expected_results": case.expected_results or [],
            "priority": case.priority or "P2",
            "category": case.category or "functional",
            # 优先使用 LLM 生成的证据引用，否则从映射表中查找
            "evidence_refs": case.evidence_refs or evidence_lookup.get(case.title, []),
            # 保留 checkpoint_id（由 draft_writer 生成）
            "checkpoint_id": case.checkpoint_id or "",
        }

        # ---- 模版字段兜底继承 ----
        # 如果 case 没有模版绑定，但关联的 checkpoint 有，则继承
        if not case.template_leaf_id and case.checkpoint_id:
            cp = cp_lookup.get(case.checkpoint_id)
            if cp and cp.template_leaf_id:
                update_fields.update({
                    "template_leaf_id": cp.template_leaf_id,
                    "template_path_ids": cp.template_path_ids,
                    "template_path_titles": cp.template_path_titles,
                    "template_match_confidence": cp.template_match_confidence,
                    "template_match_low_confidence": cp.template_match_low_confidence,
                })
                logger.info(
                    "Checklist template inheritance: case_id=%s checkpoint_id=%s "
                    "inherited_leaf_id=%s path=%s confidence=%.2f low_confidence=%s",
                    case.id or f"draft-{index}",
                    case.checkpoint_id,
                    cp.template_leaf_id,
                    " > ".join(cp.template_path_titles) or "-",
                    cp.template_match_confidence,
                    cp.template_match_low_confidence,
                )

        assembled = case.model_copy(update=update_fields)

        # 对文本字段执行中英文混排规范化
        assembled = normalize_test_case(assembled)
        assembled_cases.append(assembled)

    logger.info(
        "Checklist integration starting: draft_cases=%d optimized_tree_roots=%d "
        "checkpoint_paths=%d canonical_outline_nodes=%d template_bound_cases=%d",
        len(state.get("draft_cases", [])),
        len(state.get("optimized_tree", [])),
        len(state.get("checkpoint_paths", [])),
        len(state.get("canonical_outline_nodes", [])),
        sum(1 for case in assembled_cases if case.template_leaf_id),
    )
    for case in assembled_cases:
        logger.info(
            "Checklist pre-integration item: case_id=%s checkpoint_id=%s title=%s "
            "template_leaf_id=%s template_path=%s steps=%d expected_results=%d",
            case.id,
            case.checkpoint_id or "-",
            case.title,
            case.template_leaf_id or "-",
            " > ".join(case.template_path_titles) or "-",
            len(case.steps),
            len(case.expected_results),
        )

    optimized_tree = attach_expected_results_to_outline(
        state.get("optimized_tree", []),
        assembled_cases,
        state.get("checkpoint_paths", []),
        state.get("canonical_outline_nodes", []),
    )

    logger.info(
        "Checklist integration completed: test_cases=%d optimized_tree_roots=%d",
        len(assembled_cases),
        len(optimized_tree),
    )

    return {
        "test_cases": assembled_cases,
        "optimized_tree": optimized_tree,
    }
