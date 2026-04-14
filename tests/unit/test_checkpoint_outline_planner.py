"""Unit tests for checkpoint outline planner."""

from __future__ import annotations

import json
import re

from app.domain.checkpoint_models import Checkpoint
from app.domain.checklist_models import ChecklistNode
from app.domain.research_models import ResearchFact, ResearchOutput
from app.domain.template_models import MandatorySkeletonNode
from app.services.markdown_renderer import render_test_cases_markdown
from app.services import checkpoint_outline_planner as planner_module
from app.services.checkpoint_outline_planner import build_checkpoint_outline_planner_node


class _AdGroupOutlineLLM:
    def generate_structured(self, **kwargs):
        response_model = kwargs["response_model"]
        user_prompt = kwargs.get("user_prompt", "")
        checkpoint_ids = re.findall(
            r"Checkpoint ID:\s*(CP-[A-Za-z0-9_-]+)",
            user_prompt,
        )
        if not checkpoint_ids:
            try:
                payload = json.loads(user_prompt)
            except json.JSONDecodeError:
                payload = {}
            checkpoint_ids = [
                item["checkpoint_id"]
                for item in payload.get("checkpoints", [])
                if item.get("checkpoint_id")
            ]

        if response_model.__name__ == "CanonicalOutlineNodeCollection":
            return response_model.model_validate(
                {
                    "canonical_nodes": [
                        {
                            "node_id": "node-ad-group",
                            "semantic_key": "ad_group",
                            "display_text": "Ad group",
                            "kind": "business_object",
                            "visibility": "visible",
                            "aliases": ["ad group"],
                        },
                        {
                            "node_id": "node-cbo",
                            "semantic_key": "cbo",
                            "display_text": "CBO",
                            "kind": "context",
                            "visibility": "visible",
                            "aliases": ["CBO"],
                        },
                        {
                            "node_id": "node-launch-before",
                            "semantic_key": "launch_before",
                            "display_text": "launch 前",
                            "kind": "context",
                            "visibility": "visible",
                            "aliases": ["launch before"],
                        },
                        {
                            "node_id": "node-launch-after",
                            "semantic_key": "launch_after",
                            "display_text": "launch 后",
                            "kind": "context",
                            "visibility": "visible",
                            "aliases": ["launch after"],
                        },
                        {
                            "node_id": "node-enter-page",
                            "semantic_key": "enter_create_ad_group_page",
                            "display_text": "进入 `Create Ad Group` 页面",
                            "kind": "page",
                            "visibility": "visible",
                            "aliases": ["Create Ad Group"],
                        },
                        {
                            "node_id": "node-optimize-goal",
                            "semantic_key": "optimize_goal",
                            "display_text": "定位 `optimize goal` 区域",
                            "kind": "action",
                            "visibility": "visible",
                            "aliases": ["optimize goal"],
                        },
                    ]
                }
            )

        if response_model.__name__ == "CheckpointPathCollection":
            return response_model.model_validate(
                {
                    "checkpoint_paths": [
                        {
                            "checkpoint_id": checkpoint_ids[0],
                            "path_node_ids": [
                                "node-ad-group",
                                "node-cbo",
                                "node-launch-before",
                                "node-enter-page",
                                "node-optimize-goal",
                            ],
                        },
                        {
                            "checkpoint_id": checkpoint_ids[1],
                            "path_node_ids": [
                                "node-ad-group",
                                "node-launch-after",
                                "node-enter-page",
                                "node-optimize-goal",
                            ],
                        },
                    ]
                }
            )

        raise AssertionError(f"Unexpected response model: {response_model.__name__}")


def _sample_state() -> dict:
    return {
        "research_output": ResearchOutput(
            facts=[
                ResearchFact(
                    fact_id="FACT-001",
                    description="CBO campaigns expose optimize goal before launch for Ad group creation.",
                    category="behavior",
                ),
                ResearchFact(
                    fact_id="FACT-002",
                    description="After launch, optimize goal remains configurable on Ad group.",
                    category="behavior",
                ),
            ]
        ),
        "checkpoints": [
            Checkpoint(
                checkpoint_id="CP-001",
                title="验证 CBO 场景下 launch 前 `optimize goal` 可见",
                objective="确保创建阶段可以配置 `optimize goal`",
                preconditions=["已进入广告创建流程"],
                fact_ids=["FACT-001"],
            ),
            Checkpoint(
                checkpoint_id="CP-002",
                title="验证 launch 后 Ad group 仍可调整 `optimize goal`",
                objective="确保投放后仍可查看和调整 `optimize goal`",
                preconditions=["Ad group 已开始投放"],
                fact_ids=["FACT-002"],
            ),
        ],
    }


def test_outline_planner_keeps_context_under_visible_business_object() -> None:
    node = build_checkpoint_outline_planner_node(_AdGroupOutlineLLM())

    result = node(_sample_state())

    top_titles = [item.title for item in result["optimized_tree"]]
    assert top_titles == ["Ad group"]

    ad_group_node = result["optimized_tree"][0]
    child_titles = [child.title for child in ad_group_node.children]
    assert "CBO" in child_titles
    assert "launch 后" in child_titles
    assert "launch 前" not in top_titles
    assert "CBO" not in top_titles

    cbo_node = next(child for child in ad_group_node.children if child.title == "CBO")
    assert [child.title for child in cbo_node.children] == ["launch 前"]


def test_outline_planner_exposes_checkpoint_paths_and_outline_nodes() -> None:
    node = build_checkpoint_outline_planner_node(_AdGroupOutlineLLM())

    result = node(_sample_state())

    assert any(item.display_text == "Ad group" for item in result["canonical_outline_nodes"])
    assert len(result["checkpoint_paths"]) == 2
    assert result["checkpoint_paths"][0].path_node_ids[0] == "node-ad-group"


def test_outline_tree_renders_before_draft_cases_exist() -> None:
    node = build_checkpoint_outline_planner_node(_AdGroupOutlineLLM())

    result = node(_sample_state())
    markdown = render_test_cases_markdown([], optimized_tree=result["optimized_tree"])

    assert "## Ad group" in markdown
    assert "### CBO" in markdown
    assert "#### launch 前" in markdown
    assert "[TC-" not in markdown
    assert "Checkpoint" not in markdown
    assert "步骤" not in markdown


def test_outline_planner_node_accepts_mapping_state(monkeypatch) -> None:
    captured: dict = {}

    def _fake_plan(self, **kwargs):
        del self
        captured.update(kwargs)
        return planner_module.CheckpointOutlinePlan(
            canonical_outline_nodes=[],
            checkpoint_paths=[],
            optimized_tree=[ChecklistNode(node_id="root", title="Root")],
        )

    monkeypatch.setattr(planner_module.CheckpointOutlinePlanner, "plan", _fake_plan)

    state = {
        "research_output": ResearchOutput(),
        "checkpoints": [],
        "coverage_result": "coverage",
        "mandatory_skeleton": "mandatory",
        "xmind_reference_summary": "xmind-summary",
    }
    node = build_checkpoint_outline_planner_node(object())

    result = node(state)

    assert result == {
        "canonical_outline_nodes": [],
        "checkpoint_paths": [],
        "optimized_tree": [ChecklistNode(node_id="root", title="Root")],
    }
    assert captured["research_output"] is state["research_output"]
    assert captured["checkpoints"] == []
    assert captured["coverage_result"] == "coverage"
    assert captured["mandatory_skeleton"] == "mandatory"
    assert captured["xmind_reference"] == "xmind-summary"


def test_outline_planner_serializes_and_enforces_mandatory_skeleton() -> None:
    skeleton = MandatorySkeletonNode(
        id="__mandatory_root__",
        title="Mandatory Skeleton Root",
        depth=0,
        is_mandatory=True,
        children=[
            MandatorySkeletonNode(
                id="campaign",
                title="Campaign",
                depth=1,
                is_mandatory=True,
                children=[
                    MandatorySkeletonNode(
                        id="ad-group",
                        title="Ad group",
                        depth=2,
                        is_mandatory=False,
                        children=[
                            MandatorySkeletonNode(
                                id="optimize-goal",
                                title="Optimize goal",
                                depth=3,
                                is_mandatory=True,
                            )
                        ],
                    )
                ],
            )
        ],
    )
    node = build_checkpoint_outline_planner_node(object())

    result = node(
        {
            "research_output": ResearchOutput(),
            "checkpoints": [],
            "mandatory_skeleton": skeleton,
        }
    )

    assert [item.title for item in result["optimized_tree"]] == ["Campaign"]
    campaign = result["optimized_tree"][0]
    assert [child.title for child in campaign.children] == ["Ad group"]
    assert [child.title for child in campaign.children[0].children] == ["Optimize goal"]
