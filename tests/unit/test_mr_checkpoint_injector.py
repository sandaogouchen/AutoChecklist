"""Unit tests for MR checkpoint injector."""

from __future__ import annotations

from app.domain.checkpoint_models import Checkpoint
from app.domain.mr_models import MRCodeFact
from app.domain.template_models import TemplateLeafTarget
from app.nodes.mr_checkpoint_injector import build_mr_checkpoint_injector_node


def test_mr_checkpoint_injector_returns_checkpoint_models() -> None:
    node = build_mr_checkpoint_injector_node()

    result = node(
        {
            "checkpoints": [
                Checkpoint(
                    checkpoint_id="CP-001",
                    title="已有 PRD 检查点",
                    fact_ids=["FACT-001"],
                )
            ],
            "mr_code_facts": [
                MRCodeFact(
                    fact_id="FE-MR-FACT-001",
                    description="Custom Lineups 变更后应联动 contextual targeting",
                    source_file="apps/rf-creation/src/custom-lineups.ts",
                    fact_type="state_change",
                )
            ],
        }
    )

    assert len(result["checkpoints"]) == 2
    injected = result["checkpoints"][1]
    assert isinstance(injected, Checkpoint)
    assert injected.checkpoint_id == "FE-MR-CP-0001"
    assert injected.fact_ids == ["FE-MR-FACT-001"]
    assert injected.category == "functional"
    assert injected.title.startswith("[前端] ")


def test_mr_checkpoint_injector_inherits_template_binding_from_related_prd_checkpoint() -> None:
    node = build_mr_checkpoint_injector_node()

    result = node(
        {
            "checkpoints": [
                Checkpoint(
                    checkpoint_id="CP-001",
                    title="已有 PRD 检查点",
                    fact_ids=["FACT-001"],
                    template_leaf_id="leaf-code-logic",
                    template_path_ids=["root-risk", "leaf-code-logic"],
                    template_path_titles=["风险检查", "代码实现逻辑"],
                    template_match_confidence=0.91,
                    template_match_reason="该检查点已绑定到代码实现逻辑叶子",
                )
            ],
            "template_leaf_targets": [
                TemplateLeafTarget(
                    leaf_id="leaf-code-logic",
                    leaf_title="代码实现逻辑",
                    path_ids=["root-risk", "leaf-code-logic"],
                    path_titles=["风险检查", "代码实现逻辑"],
                    path_text="风险检查 > 代码实现逻辑",
                )
            ],
            "mr_code_facts": [
                MRCodeFact(
                    fact_id="MR-FACT-001",
                    description="代码实际走降级逻辑",
                    source_file="app/example.ts",
                    fact_type="code_logic",
                    related_prd_fact_ids=["FACT-001"],
                )
            ],
        }
    )

    injected = result["checkpoints"][1]
    assert injected.template_leaf_id == "leaf-code-logic"
    assert injected.template_path_ids == ["root-risk", "leaf-code-logic"]
    assert injected.template_path_titles == ["风险检查", "代码实现逻辑"]
    assert injected.template_match_reason
