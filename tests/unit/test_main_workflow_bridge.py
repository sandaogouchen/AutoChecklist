"""Workflow bridge regression tests for MR/Coco state propagation."""

from __future__ import annotations

from app.domain.research_models import ResearchOutput
from app.graphs import main_workflow as main_workflow_module
from app.graphs.main_workflow import build_workflow


class _FakeSubgraph:
    def invoke(self, _state):
        return {
            "planned_scenarios": [],
            "checkpoints": [],
            "checkpoint_coverage": [],
            "draft_cases": [],
            "test_cases": [],
            "optimized_tree": [],
            "coverage_result": {"covered": 1},
            "mr_analysis_result": {"summary": "mr ok"},
            "mr_code_facts": [{"fact_id": "MR-FACT-001"}],
            "mr_consistency_issues": [{"issue_id": "ISSUE-001"}],
            "mr_combined_summary": "combined summary",
            "frontend_mr_result": {"side": "frontend"},
            "backend_mr_result": {"side": "backend"},
            "coco_validation_summary": {"confirmed": 2},
            "coco_artifacts": {"task1_frontend_result": "/tmp/task1.json"},
            "mira_artifacts": {"task2_results": "/tmp/mira-task2.json"},
            "coco_cache_dir": "/tmp/coco",
            "coco_cache_run_id": "run-cache",
            "checkpoint_paths": [{"checkpoint_id": "CP-001", "path_node_ids": ["node-1"]}],
            "canonical_outline_nodes": [{"node_id": "node-1", "display_text": "Node 1"}],
            "mapped_evidence": {"Scenario": []},
        }


def test_build_workflow_promotes_mr_and_coco_outputs_from_case_generation(monkeypatch) -> None:
    monkeypatch.setattr(
        main_workflow_module,
        "build_case_generation_subgraph",
        lambda *args, **kwargs: _FakeSubgraph(),
    )
    monkeypatch.setattr(main_workflow_module, "input_parser_node", lambda state: {})
    monkeypatch.setattr(
        main_workflow_module,
        "build_template_loader_node",
        lambda: (lambda state: {}),
    )
    monkeypatch.setattr(
        main_workflow_module,
        "build_context_research_node",
        lambda _llm: (lambda state: {}),
    )
    monkeypatch.setattr(main_workflow_module, "reflection_node", lambda state: {})

    workflow = build_workflow(llm_client=object())
    result = workflow.invoke(
        {
            "parsed_document": {"title": "doc"},
            "research_output": ResearchOutput(),
            "frontend_mr_config": {"mr_url": "https://example.com/fe/merge_requests/1"},
            "backend_mr_config": {"mr_url": "https://example.com/be/merge_requests/2"},
            "run_output_dir": "/tmp/run-output",
        }
    )

    assert result["mr_analysis_result"] == {"summary": "mr ok"}
    assert result["mr_code_facts"] == [{"fact_id": "MR-FACT-001"}]
    assert result["mr_consistency_issues"] == [{"issue_id": "ISSUE-001"}]
    assert result["mr_combined_summary"] == "combined summary"
    assert result["frontend_mr_result"] == {"side": "frontend"}
    assert result["backend_mr_result"] == {"side": "backend"}
    assert result["coco_validation_summary"] == {"confirmed": 2}
    assert result["coco_artifacts"] == {"task1_frontend_result": "/tmp/task1.json"}
    assert result["mira_artifacts"] == {"task2_results": "/tmp/mira-task2.json"}
    assert result["coco_cache_dir"] == "/tmp/coco"
    assert result["coco_cache_run_id"] == "run-cache"
    assert result["checkpoint_paths"] == [
        {"checkpoint_id": "CP-001", "path_node_ids": ["node-1"]}
    ]
    assert result["canonical_outline_nodes"] == [
        {"node_id": "node-1", "display_text": "Node 1"}
    ]
    assert result["mapped_evidence"] == {"Scenario": []}
