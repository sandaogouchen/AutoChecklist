from __future__ import annotations

from app.domain.checkpoint_models import Checkpoint
from app.domain.mr_models import MRCodeFact
from app.graphs import case_generation as case_generation_module
from app.graphs.case_generation import build_case_generation_subgraph


class _NoopDraftWriter:
    def __init__(self, _llm_client) -> None:
        pass

    def __call__(self, state):
        return {"draft_cases": state.get("draft_cases", [])}


def test_case_generation_keeps_mr_injected_checkpoints_as_supplement(monkeypatch) -> None:
    def _fake_build_mr_analyzer_node(**kwargs):
        del kwargs

        def _node(_state):
            return {
                "mr_code_facts": [
                    MRCodeFact(
                        fact_id="MR-FACT-001",
                        description="补充的 MR 检查点",
                        source_file="app/example.ts",
                        fact_type="boundary",
                    )
                ]
            }

        return _node

    def _fake_checkpoint_generator_node(_state):
        return {
            "checkpoints": [
                Checkpoint(checkpoint_id="CP-PRD", title="PRD 检查点")
            ]
        }

    monkeypatch.setattr(case_generation_module, "build_mr_analyzer_node", _fake_build_mr_analyzer_node)
    monkeypatch.setattr(case_generation_module, "scenario_planner_node", lambda state: {"planned_scenarios": []})
    monkeypatch.setattr(case_generation_module, "build_checkpoint_generator_node", lambda _llm: _fake_checkpoint_generator_node)
    monkeypatch.setattr(case_generation_module, "checkpoint_evaluator_node", lambda state: {"checkpoints": state.get("checkpoints", [])})
    monkeypatch.setattr(case_generation_module, "_coverage_detector_node", lambda state: {"coverage_result": None, "uncovered_checkpoints": state.get("checkpoints", [])})
    monkeypatch.setattr(case_generation_module, "build_checkpoint_outline_planner_node", lambda _llm: (lambda state: {"optimized_tree": [], "checkpoint_paths": [], "canonical_outline_nodes": []}))
    monkeypatch.setattr(case_generation_module, "evidence_mapper_node", lambda state: {"mapped_evidence": {}})
    monkeypatch.setattr(case_generation_module, "DraftWriterNode", _NoopDraftWriter)
    monkeypatch.setattr(case_generation_module, "build_coco_consistency_validator_node", lambda **kwargs: (lambda state: {}))
    monkeypatch.setattr(case_generation_module, "structure_assembler_node", lambda state: {"test_cases": [], "optimized_tree": state.get("optimized_tree", [])})

    subgraph = build_case_generation_subgraph(llm_client=object())
    result = subgraph.invoke({"research_output": {"facts": []}})

    titles = []
    for cp in result["checkpoints"]:
        if isinstance(cp, dict):
            titles.append(cp.get("title", ""))
        else:
            titles.append(cp.title)

    assert "PRD 检查点" in titles
    assert "补充的 MR 检查点" in titles
    assert len(titles) == 2
