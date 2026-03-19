"""Unit tests for draft writer path-constrained mode."""

from __future__ import annotations

from app.domain.checklist_models import CanonicalOutlineNode, CheckpointPathMapping
from app.domain.checkpoint_models import Checkpoint
from app.nodes.draft_writer import build_draft_writer_node


class _SpyDraftWriterLLM:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    def generate_structured(self, **kwargs):
        self.system_prompt = kwargs["system_prompt"]
        self.user_prompt = kwargs["user_prompt"]
        response_model = kwargs["response_model"]
        return response_model.model_validate(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "title": "验证 `optimize goal` 字段交互",
                        "preconditions": ["用户已登录系统"],
                        "steps": [
                            "打开 `Create Ad Group` 页面",
                            "查看 `optimize goal` 字段状态",
                        ],
                        "expected_results": [
                            "`optimize goal` 字段显示正确且允许交互。"
                        ],
                        "priority": "P1",
                        "category": "functional",
                        "checkpoint_id": "CP-001",
                        "evidence_refs": [],
                    }
                ]
            }
        )


def test_draft_writer_uses_fixed_hierarchy_path_context() -> None:
    llm_client = _SpyDraftWriterLLM()
    node = build_draft_writer_node(llm_client)

    result = node(
        {
            "checkpoints": [
                Checkpoint(
                    checkpoint_id="CP-001",
                    title="验证 `optimize goal` 字段",
                    objective="确认创建阶段可以查看并设置 `optimize goal`",
                    category="functional",
                    risk="high",
                    preconditions=["用户已登录系统"],
                )
            ],
            "checkpoint_paths": [
                CheckpointPathMapping(
                    checkpoint_id="CP-001",
                    path_node_ids=[
                        "node-ad-group",
                        "node-cbo",
                        "node-launch-before",
                        "node-optimize-goal",
                    ],
                )
            ],
            "canonical_outline_nodes": [
                CanonicalOutlineNode(
                    node_id="node-ad-group",
                    semantic_key="ad_group",
                    display_text="Ad group",
                    kind="business_object",
                    visibility="visible",
                ),
                CanonicalOutlineNode(
                    node_id="node-cbo",
                    semantic_key="cbo",
                    display_text="CBO",
                    kind="context",
                    visibility="visible",
                ),
                CanonicalOutlineNode(
                    node_id="node-launch-before",
                    semantic_key="launch_before",
                    display_text="launch 前",
                    kind="context",
                    visibility="visible",
                ),
                CanonicalOutlineNode(
                    node_id="node-optimize-goal",
                    semantic_key="optimize_goal",
                    display_text="定位 `optimize goal` 区域",
                    kind="action",
                    visibility="visible",
                ),
            ],
        }
    )

    assert result["draft_cases"][0].title == "验证 `optimize goal` 字段交互"
    assert "Ad group" in llm_client.user_prompt
    assert "launch 前" in llm_client.user_prompt
    assert "Fixed hierarchy path" in llm_client.user_prompt
    assert "Do not restate" in llm_client.system_prompt
    assert "merged parent phrases" in llm_client.system_prompt
    assert "Ad group" not in result["draft_cases"][0].title
    assert "CBO" not in result["draft_cases"][0].title
