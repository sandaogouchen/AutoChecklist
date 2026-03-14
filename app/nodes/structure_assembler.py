from __future__ import annotations

from app.domain.case_models import TestCase
from app.domain.state import CaseGenState


def structure_assembler_node(state: CaseGenState) -> CaseGenState:
    draft_cases = state.get("draft_cases", [])
    evidence_lookup = state.get("mapped_evidence", {})
    grouped_cases = _group_cases(draft_cases)
    assembled_roots: list[TestCase] = []

    for root_index, (group_key, cases) in enumerate(grouped_cases, start=1):
        assembled_roots.append(
            _assemble_group(
                cases=cases,
                group_key=group_key,
                root_index=root_index,
                default_evidence=evidence_lookup.get(group_key, []),
            )
        )

    return {"test_cases": assembled_roots}


def _group_cases(draft_cases: list[TestCase]) -> list[tuple[str, list[TestCase]]]:
    grouped: dict[str, list[TestCase]] = {}
    order: list[str] = []
    for case in draft_cases:
        group_key = case.fact_id.strip() or case.title.strip() or case.id.strip()
        if group_key not in grouped:
            grouped[group_key] = []
            order.append(group_key)
        grouped[group_key].append(case)
    return [(group_key, grouped[group_key]) for group_key in order]


def _assemble_group(
    *,
    cases: list[TestCase],
    group_key: str,
    root_index: int,
    default_evidence: list,
) -> TestCase:
    root_position = _find_root_position(cases)
    original_ids = [case.id.strip() or f"draft-{root_index}-{index}" for index, case in enumerate(cases, start=1)]
    id_to_position = {original_id: index for index, original_id in enumerate(original_ids)}
    children_by_parent: dict[int, list[int]] = {index: [] for index in range(len(cases))}

    for index, case in enumerate(cases):
        if index == root_position:
            continue
        parent_position = _resolve_parent_position(case.parent, id_to_position, root_position)
        children_by_parent[parent_position].append(index)

    root_case = cases[root_position]
    root_id = root_case.id.strip() or f"TC-{root_index:03d}"

    def build_node(position: int, parent_id: str | None, current_id: str, root_id: str) -> TestCase:
        case = cases[position]
        child_indices = children_by_parent.get(position, [])
        built_children = [
            build_node(
                child_position,
                current_id,
                cases[child_position].id.strip() or f"{current_id}-{offset:02d}",
                root_id,
            )
            for offset, child_position in enumerate(child_indices, start=1)
        ]
        wired_children = _wire_siblings(built_children)
        return case.model_copy(
            update={
                "id": current_id,
                "fact_id": case.fact_id or group_key,
                "node_type": "root" if position == root_position else (case.node_type or "check"),
                "branch": case.branch or "main",
                "parent": parent_id,
                "root": root_id,
                "prev": None,
                "next": None,
                "preconditions": case.preconditions or [],
                "steps": case.steps or [],
                "expected_results": case.expected_results or [],
                "priority": case.priority or "P2",
                "category": case.category or "functional",
                "evidence_refs": case.evidence_refs or default_evidence,
                "children": wired_children,
            }
        )

    return build_node(root_position, None, root_id, root_id)


def _find_root_position(cases: list[TestCase]) -> int:
    for index, case in enumerate(cases):
        if case.node_type == "root":
            return index
    for index, case in enumerate(cases):
        if not case.parent:
            return index
    return 0


def _resolve_parent_position(
    parent_id: str | None,
    id_to_position: dict[str, int],
    root_position: int,
) -> int:
    if parent_id and parent_id in id_to_position and id_to_position[parent_id] != root_position:
        return id_to_position[parent_id]
    return root_position


def _wire_siblings(children: list[TestCase]) -> list[TestCase]:
    wired_children: list[TestCase] = []
    for index, child in enumerate(children):
        wired_children.append(
            child.model_copy(
                update={
                    "prev": children[index - 1].id if index > 0 else None,
                    "next": children[index + 1].id if index + 1 < len(children) else None,
                }
            )
        )
    return wired_children
