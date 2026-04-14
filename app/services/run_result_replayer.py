from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.domain.api_models import CaseGenerationRun
from app.domain.case_models import TestCase
from app.domain.checklist_models import ChecklistNode
from app.domain.checkpoint_models import Checkpoint
from app.domain.research_models import ResearchOutput
from app.services.markdown_renderer import render_test_cases_markdown
from app.services.xmind_connector import FileXMindConnector
from app.services.xmind_delivery_agent import XMindDeliveryAgent
from app.services.xmind_payload_builder import XMindPayloadBuilder

_BACKTICK_TEXT_PATTERN = re.compile(r"`([^`]+)`")


@dataclass
class ReplayDeliveryResult:
    selected_case_count: int
    markdown_path: str
    xmind_path: str


def replay_delivery_from_run_result(
    run_result_path: str | Path,
    *,
    output_dir: str | Path | None = None,
) -> ReplayDeliveryResult:
    run_result_file = Path(run_result_path)
    run = CaseGenerationRun.model_validate(
        json.loads(run_result_file.read_text(encoding="utf-8"))
    )

    run_dir = run_result_file.parent
    checkpoints = _load_checkpoints_from_artifacts(run_dir, run.artifacts)
    selected_cases = _select_actionable_cases(run.test_cases, checkpoints)

    if not checkpoints:
        checkpoints = _derive_checkpoints_from_cases(selected_cases)

    return _replay_delivery(
        test_cases=selected_cases,
        checkpoints=checkpoints,
        research_output=run.research_summary,
        output_dir=output_dir or run_dir,
        title=run.input.file_path if run.input else run_result_file.stem,
        run_id=run.run_id,
    )


def replay_delivery_from_testcase_json(
    testcase_json_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    title: str = "",
) -> ReplayDeliveryResult:
    testcase_file = Path(testcase_json_path)
    test_cases = [
        TestCase.model_validate(item)
        for item in json.loads(testcase_file.read_text(encoding="utf-8"))
    ]
    checkpoints = _derive_checkpoints_from_cases(test_cases)

    return _replay_delivery(
        test_cases=test_cases,
        checkpoints=checkpoints,
        research_output=None,
        output_dir=output_dir or testcase_file.parent,
        title=title or testcase_file.stem,
        run_id=testcase_file.parent.name,
    )


def _replay_delivery(
    *,
    test_cases: list[TestCase],
    checkpoints: list[Checkpoint],
    research_output: ResearchOutput | None,
    output_dir: str | Path,
    title: str,
    run_id: str,
) -> ReplayDeliveryResult:
    replay_dir = Path(output_dir)
    replay_dir.mkdir(parents=True, exist_ok=True)

    optimized_tree = _build_precondition_group_tree(test_cases)
    markdown_path = replay_dir / "replayed_test_cases.md"
    markdown_path.write_text(
        render_test_cases_markdown(test_cases, optimized_tree=optimized_tree),
        encoding="utf-8",
    )

    agent = XMindDeliveryAgent(
        connector=FileXMindConnector(output_dir=replay_dir),
        payload_builder=XMindPayloadBuilder(),
        output_dir=replay_dir,
    )
    xmind_result = agent.deliver(
        run_id=run_id,
        test_cases=test_cases,
        checkpoints=checkpoints,
        research_output=research_output,
        optimized_tree=optimized_tree,
        title=title,
        output_dir=replay_dir,
    )
    if not xmind_result.success:
        raise ValueError(xmind_result.error_message or "XMind replay delivery failed")

    return ReplayDeliveryResult(
        selected_case_count=len(test_cases),
        markdown_path=str(markdown_path),
        xmind_path=xmind_result.file_path,
    )


def _load_checkpoints_from_artifacts(
    run_dir: Path,
    artifacts: dict[str, str],
) -> list[Checkpoint]:
    checkpoints_path = artifacts.get("checkpoints")
    if not checkpoints_path:
        return []

    candidate = Path(checkpoints_path)
    if not candidate.is_absolute():
        candidate = run_dir / candidate
    if not candidate.exists():
        candidate = run_dir / Path(checkpoints_path).name
    if not candidate.exists():
        return []

    raw_items = json.loads(candidate.read_text(encoding="utf-8"))
    return [Checkpoint.model_validate(item) for item in raw_items]


def _select_actionable_cases(
    test_cases: list[TestCase],
    checkpoints: list[Checkpoint],
) -> list[TestCase]:
    checkpoint_ids = {
        checkpoint.checkpoint_id
        for checkpoint in checkpoints
        if checkpoint.checkpoint_id
    }
    selected: list[TestCase] = []
    for case in test_cases:
        if checkpoint_ids:
            if case.checkpoint_id in checkpoint_ids:
                selected.append(case)
            continue
        if _looks_like_reference_case(case):
            continue
        selected.append(case)
    return selected


def _looks_like_reference_case(case: TestCase) -> bool:
    checkpoint_id = (case.checkpoint_id or "").lower()
    title = case.title.strip()
    return checkpoint_id.startswith("ref-") or title.startswith("参考")


def _derive_checkpoints_from_cases(test_cases: list[TestCase]) -> list[Checkpoint]:
    checkpoints: list[Checkpoint] = []
    seen_ids: set[str] = set()
    for case in test_cases:
        checkpoint_id = case.checkpoint_id or case.id
        if checkpoint_id in seen_ids:
            continue
        checkpoints.append(
            Checkpoint(
                checkpoint_id=checkpoint_id,
                title=case.title,
                objective=case.expected_results[0] if case.expected_results else "",
                category=case.category,
                preconditions=list(case.preconditions),
                evidence_refs=list(case.evidence_refs),
            )
        )
        seen_ids.add(checkpoint_id)
    return checkpoints


def _build_precondition_group_tree(
    test_cases: list[TestCase],
) -> list[ChecklistNode]:
    groups: dict[str, list[TestCase]] = {}
    for case in test_cases:
        group_title = _extract_group_title(case)
        groups.setdefault(group_title, []).append(case)

    tree: list[ChecklistNode] = []
    for index, (group_title, cases) in enumerate(groups.items(), start=1):
        tree.append(
            ChecklistNode(
                node_id=f"replay-group-{index}",
                title=group_title,
                node_type="precondition_group",
                children=[_build_case_node(case) for case in cases],
            )
        )
    return tree


def _extract_group_title(case: TestCase) -> str:
    for text in [*case.preconditions, *case.steps]:
        match = _BACKTICK_TEXT_PATTERN.search(text)
        if match:
            return match.group(1)
    if case.preconditions:
        return case.preconditions[0]
    if case.steps:
        return case.steps[0]
    return "未分组"


def _build_case_node(case: TestCase) -> ChecklistNode:
    return ChecklistNode(
        node_id=case.id,
        title=case.title,
        node_type="case",
        test_case_ref=case.id,
        preconditions=list(case.preconditions),
        steps=list(case.steps),
        expected_results=list(case.expected_results),
        priority=case.priority,
        category=case.category,
        evidence_refs=list(case.evidence_refs),
        checkpoint_id=case.checkpoint_id,
    )
